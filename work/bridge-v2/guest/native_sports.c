/* Experimental native sport-display adapter; not included in production builds.
 *
 * Evidence: outputs/native-integration/sports-hooks.json, original HmiMain3D
 * SHA256 554b67d4d6317cfb1715d544874fae8ddd2c975be503c9e2514e2dc2f3a0d693.
 * Addresses and complete overwritten instructions are identity checked before
 * any write. This changes private guest process memory, never firmware on disk.
 *
 * QNX mman constants/signature verified against public OpenQNX sys/mman.h:
 * https://raw.githubusercontent.com/vocho/openqnx/master/trunk/lib/c/public/sys/mman.h
 *
 * Interface for root bridge integration:
 * int nbt_sports_init(void);             called by constructor, idempotent
 * int nbt_sports_update(unsigned, unsigned);  queue channel0/1 percentages
 * void nbt_sports_tick(void);            ONLY from the GUI rendering thread
 *
 * Channel-to-physical-unit mapping is deliberately not guessed. Percentages
 * are the actual bounded inputs to the original gauge-animation helper.
 */
#include "nbt_guest.h"

NBT_IMPORT int mprotect(void *address, size_t length, int protection);

#define SPORTS_INIT       0x088D3FD0u
#define SPORTS_DTOR0      0x088D4484u
#define SPORTS_DTOR1      0x088D452Eu
#define SPORTS_VTABLE     0x095F7668u
#define SPORTS_SET_VALUE  0x0934DE0Eu
#define SPORTS_AVAILABILITY 0x088D0B72u
#define QNX_PROT_RX       0x500
#define QNX_PROT_RWX      0x700
#define QNX_MAP_PRIV_ANON 0x80002
#define PAGE_BYTES       4096u

typedef uint32_t (*sports_method)(void *);
typedef void (*sports_value_method)(void *, uint32_t, uint32_t);

typedef struct sports_hook {
    uintptr_t address;
    uint8_t identity[16];
    void *replacement;
    sports_method original;
    int installed;
} sports_hook;

static volatile uint32_t g_table;
static qnx_pthread_t g_owner;
static volatile uint32_t g_values;
static volatile uint32_t g_sequence;
static uint32_t g_seen_sequence;
static uint32_t g_applied;
static int g_initialized;
static int g_enabled;
static int g_thread_warning;
static uint64_t g_last_log;
static volatile int g_tick_busy;
static uint32_t g_configured_helper;

static inline uintptr_t native_addr(uintptr_t address)
{
    /* Prevent the PIC linker resolving an absolute firmware call as rel32. */
    __asm__ __volatile__("" : "+r"(address));
    return address;
}

static uint32_t init_capture(void *self);
static uint32_t dtor0_capture(void *self);
static uint32_t dtor1_capture(void *self);
static uint32_t availability_override(void *self, int terminal_ready);

static sports_hook g_hooks[4] = {
    { SPORTS_INIT,
      { 0x55,0x89,0xe5,0x57,0x56,0x53,0x83,0xec,0x7c,0x8b,0x5d,0x08,0xe8,0x0e,0xe2,0x22 },
      (void *)init_capture, (sports_method)0, 0 },
    { SPORTS_DTOR0,
      { 0x55,0x89,0xe5,0x56,0x53,0x8b,0x5d,0x08,0xc7,0x03,0x68,0x76,0x5f,0x09,0xc7,0x43 },
      (void *)dtor0_capture, (sports_method)0, 0 },
    { SPORTS_DTOR1,
      { 0x55,0x89,0xe5,0x56,0x53,0x8b,0x5d,0x08,0xc7,0x03,0x68,0x76,0x5f,0x09,0xc7,0x43 },
      (void *)dtor1_capture, (sports_method)0, 0 },
    { SPORTS_AVAILABILITY,
      {0x55,0x89,0xe5,0x57,0x56,0x53,0x83,0xec,0x1c,0x8b,0x5d,0x08,0x8a,0x45,0x0c,0x88},
      (void *)availability_override, (sports_method)0, 0 }
};

static uint32_t rd32(uintptr_t address) { return *(volatile uint32_t *)address; }

static void emit_jump(uint8_t *destination, uintptr_t target)
{
    uint32_t displacement = (uint32_t)(target - ((uintptr_t)destination + 5));
    destination[0] = 0xe9;
    memcpy(destination + 1, &displacement, 4);
}

static int replace_entry(sports_hook *hook, int install)
{
    uintptr_t page = hook->address & ~(uintptr_t)(PAGE_BYTES - 1);
    if (nbt_native_writable_page(page) != 0) {
        NBT_LOG("NBT_SPORTS_HOOK_PROTECT_FAILED address=%x errno=%d\n", (unsigned)hook->address, nbt_errno());
        return -1;
    }
    if (install) emit_jump((uint8_t *)hook->address, (uintptr_t)hook->replacement);
    else memcpy((void *)hook->address, hook->identity, 5);
    nbt_mb();
    hook->installed = install;
    if (mprotect((void *)page, PAGE_BYTES, QNX_PROT_RX) != 0) {
        /* Do not pretend the hook failed: the write already happened. */
        NBT_LOG("NBT_SPORTS_HOOK_RX_RESTORE_FAILED address=%x errno=%d\n", (unsigned)hook->address, nbt_errno());
        return -1;
    }
    return 0;
}

NBT_API int nbt_sports_init(void)
{
    if (g_initialized) return g_enabled ? 0 : -1;
    g_initialized = 1;
    const char *setting = getenv("NBT_NATIVE_SPORTS");
#ifdef NBT_EXPERIMENTAL_NATIVE
    int requested = !setting || strcmp(setting, "0") != 0;
#else
    int requested = setting && strcmp(setting, "1") == 0;
#endif
    if (!requested) return -1;
    const uint8_t helper_identity[16] = {
        0x55,0x89,0xe5,0x83,0xec,0x08,0x8b,0x45,0x08,0x8b,0x55,0x0c,0x8b,0x4d,0x10,0x85
    };
    for (unsigned i = 0; i < 4; ++i) {
        if (memcmp((const void *)g_hooks[i].address, g_hooks[i].identity, 16) != 0) {
            NBT_LOG("NBT_SPORTS_IDENTITY_FAILED address=%x\n", (unsigned)g_hooks[i].address);
            return -1;
        }
    }
    if (memcmp((const void *)(uintptr_t)SPORTS_SET_VALUE, helper_identity, 16) != 0) {
        NBT_LOG("NBT_SPORTS_IDENTITY_FAILED address=%x\n", SPORTS_SET_VALUE);
        return -1;
    }
    uint8_t *trampolines = (uint8_t *)mmap64((void *)0, PAGE_BYTES, QNX_PROT_RW,
                                          QNX_MAP_PRIV_ANON, QNX_NOFD, 0);
    if (trampolines == (void *)-1) {
        NBT_LOG("NBT_SPORTS_TRAMPOLINE_FAILED errno=%d\n", nbt_errno());
        return -1;
    }
    for (unsigned i = 0; i < 4; ++i) {
        uint8_t *entry = trampolines + i * 16;
        /* First five bytes are whole instructions, with no relative operands. */
        memcpy(entry, g_hooks[i].identity, 5);
        emit_jump(entry + 5, g_hooks[i].address + 5);
        g_hooks[i].original = (sports_method)(uintptr_t)entry;
    }
    if (mprotect(trampolines, PAGE_BYTES, QNX_PROT_RX) != 0) {
        NBT_LOG("NBT_SPORTS_TRAMPOLINE_EXEC_FAILED errno=%d\n", nbt_errno());
        return -1;
    }
    /* Constructor runs before HMI worker threads. Never install from tick. */
    for (unsigned i = 0; i < 4; ++i) {
        if (replace_entry(&g_hooks[i], 1) != 0) {
            for (unsigned j = 0; j <= i; ++j)
                if (g_hooks[j].installed) (void)replace_entry(&g_hooks[j], 0);
            NBT_LOG("NBT_SPORTS_INSTALL_FAILED\n");
            return -1;
        }
    }
    g_enabled = 1;
    NBT_LOG("NBT_SPORTS_HOOKS_INSTALLED identity=554b67d4 init=%x dtor0=%x dtor1=%x\n",
            SPORTS_INIT, SPORTS_DTOR0, SPORTS_DTOR1);
    return 0;
}

static uint32_t init_capture(void *self)
{
    uint32_t result = g_hooks[0].original(self);
    if (rd32((uintptr_t)self) == SPORTS_VTABLE) {
        g_owner = pthread_self();
        g_table = (uint32_t)(uintptr_t)self;
        nbt_mb();
        g_seen_sequence = 0;
        g_configured_helper = 0;
        NBT_LOG("NBT_SPORTS_INSTANCE_CAPTURED self=%p helper=%p owner_thread=%d active=%u\n",
                self, (void *)(uintptr_t)rd32((uintptr_t)self + 0x38), g_owner,
                (unsigned)*(volatile uint8_t *)((uintptr_t)self + 0x98));
    }
    return result;
}

static void invalidate(void *self)
{
    if (g_table == (uint32_t)(uintptr_t)self) {
        g_table = 0;
        nbt_mb();
        NBT_LOG("NBT_SPORTS_INSTANCE_DESTROYED self=%p\n", self);
    }
}

static uint32_t dtor0_capture(void *self)
{
    invalidate(self);
    return g_hooks[1].original(self);
}

static uint32_t dtor1_capture(void *self)
{
    invalidate(self);
    return g_hooks[2].original(self);
}

static uint32_t availability_override(void *self, int terminal_ready)
{
    /* The factory's terminal-state callback enables sport subactivities only
     * for terminal states 2/3. This profile supplies a simulated ready terminal
     * through that original callback, including its native notifications. */
    typedef uint32_t (*availability_method)(void *,int);
    uint32_t result=((availability_method)g_hooks[3].original)(self,1);
    static int logged;
    if (!logged) {
        logged=1;
        NBT_LOG("NBT_SPORTS_SIMULATED_TERMINAL_READY self=%p original_ready=%d\n",self,terminal_ready);
    }
    return result;
}

NBT_API int nbt_sports_update(unsigned channel0_percent, unsigned channel1_percent)
{
    if (!g_enabled || channel0_percent > 100 || channel1_percent > 100) return -1;
    /* One atomic word carries both channels; latest update wins. */
    __sync_lock_test_and_set(&g_values, channel0_percent | (channel1_percent << 16));
    __sync_add_and_fetch(&g_sequence, 1);
    return 0;
}

static void sports_tick_impl(void)
{
    static uint64_t last_state_log;
    uint64_t state_now = nbt_monotonic_ns();
    if (!last_state_log || state_now - last_state_log > 5000000000ull) {
        last_state_log = state_now;
        NBT_LOG("NBT_SPORTS_TICK_STATE enabled=%d table=%x sequence=%u rendering=%d owner=%d active=%u\n",
                g_enabled, g_table, g_sequence, pthread_self(), g_owner,
                g_table?(unsigned)*(volatile uint8_t *)(g_table+0x98):0);
    }
    if (!g_enabled || !g_table) return;
    qnx_pthread_t thread = pthread_self();
    if (thread != g_owner) {
        if (!g_thread_warning) {
            g_thread_warning = 1;
            NBT_LOG("NBT_SPORTS_RENDER_THREAD_MISMATCH owner=%d rendering=%d updates_disabled=1\n", g_owner, thread);
        }
        return;
    }
    if (!g_sequence) return;
    uint32_t sequence = g_sequence;
    if (sequence == g_seen_sequence) return;
    uintptr_t table = g_table;
    if (rd32(table) != SPORTS_VTABLE) {
        g_table = 0;
        NBT_LOG("NBT_SPORTS_INSTANCE_IDENTITY_LOST\n");
        return;
    }
    void *helper = (void *)(uintptr_t)rd32(table + 0x38);
    if (!helper) return;
    if (!rd32((uintptr_t)helper+8) || !rd32((uintptr_t)helper+12)) return;
    if (!*(volatile uint8_t *)(table + 0x98)) {
        typedef void (*enable_table)(void *,int);
        ((enable_table)native_addr(0x088d3de0))((void *)table,1);
    }
    if (g_configured_helper!=(uint32_t)(uintptr_t)helper) {
        typedef void (*scale_setter)(void *,uint32_t,uint32_t);
        /* Original label builder multiplies this increment by eight.
         * 50/100 therefore displays full scales of 400 kW / 800 Nm. */
        ((scale_setter)native_addr(0x0934e4a8))(helper,50,0);
        ((scale_setter)native_addr(0x0934e4a8))(helper,100,1);
        g_configured_helper=(uint32_t)(uintptr_t)helper;
        NBT_LOG("NBT_SPORTS_SIMULATOR_SCALE power=400 torque=800\n");
    }
    uint32_t values = g_values;
    uint32_t channel0 = values & 0xffffu, channel1 = values >> 16;
    if (channel0 > 100 || channel1 > 100) return;
    sports_value_method setter = (sports_value_method)native_addr(SPORTS_SET_VALUE);
    setter(helper, channel0, 0);
    setter(helper, channel1, 1);
    g_seen_sequence = sequence;
    ++g_applied;
    uint64_t now = nbt_monotonic_ns();
    if (g_applied == 1 || now - g_last_log >= 1000000000ull) {
        g_last_log = now;
        NBT_LOG("NBT_SPORTS_NATIVE_UPDATE self=%p helper=%p channel0=%u channel1=%u sequence=%u applied=%u\n",
                (void *)table, helper, channel0, channel1, sequence, g_applied);
    }
}

NBT_API void nbt_sports_tick(void)
{
    if (__sync_lock_test_and_set(&g_tick_busy,1)) return;
    sports_tick_impl();
    __sync_lock_release(&g_tick_busy);
}

__attribute__((constructor)) static void native_sports_constructor(void)
{
    (void)nbt_sports_init();
}
