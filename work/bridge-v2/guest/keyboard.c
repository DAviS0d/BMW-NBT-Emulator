/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): keyboard HAL - validates 0xFE packets and posts native HMI key events.
 */
#include "nbt_guest.h"

/* Fixed addresses of the original non-PIE HmiMain3D (SHA256 554b67d4...0d693). Read-only use. */
#define ADDR_LEGACY_GETTER   0x080B45D8u
#define ADDR_CONTEXT_GETTER  0x080B007Eu
#define ADDR_PROC_GETTER     0x08A0A732u
#define ADDR_EVENT_FACTORY   0x080968A0u
#define ADDR_SINGLETON_GUARD 0x098C0F50u
#define ADDR_TYPE_U16        0x09906D8Cu
#define ADDR_TYPE_TAG        0x09906D88u
#define TYPE_TAG_VALUE       0x096218CAu

typedef void *(*fn_void)(void);
typedef void *(*fn_this)(void *);
typedef void *(*fn_this_int)(void *, int);
typedef unsigned char (*fn_post)(void *, void *);

static const uint8_t k_ident[4][16] = {
    { 0x55, 0x89, 0xE5, 0x83, 0xEC, 0x08, 0x80, 0x3D, 0x50, 0x0F, 0x8C, 0x09, 0x00, 0x75, 0x47, 0x83 },
    { 0x55, 0x89, 0xE5, 0x53, 0x83, 0xEC, 0x04, 0x8B, 0x5D, 0x08, 0x83, 0xBB, 0xC4, 0x00, 0x00, 0x00 },
    { 0x55, 0x89, 0xE5, 0x83, 0xEC, 0x20, 0x8B, 0x45, 0x08, 0x8B, 0x10, 0x6A, 0x0E, 0x50, 0xFF, 0x52 },
    { 0x55, 0x89, 0xE5, 0x56, 0x53, 0x0F, 0xB7, 0x1D, 0x8C, 0x6D, 0x90, 0x09, 0xC1, 0xE3, 0x10, 0x81 },
};
static const uint32_t k_ident_addr[4] = { ADDR_LEGACY_GETTER, ADDR_CONTEXT_GETTER, ADDR_PROC_GETTER, ADDR_EVENT_FACTORY };

static uint32_t g_posted;

typedef struct sink {
    int ready;           /* queue_ready */
    uint32_t type;
    void *context, *proc;
    fn_this_int getter4; /* vtable(context)[4] */
    fn_post post;
} sink;

/* Absolute firmware code address -> callable pointer. The asm barrier hides the constant from the
 * compiler: otherwise clang emits a PC-relative "call rel32" that the linker resolves for load base 0,
 * so inside the PIC library the call would land at firmware_address + library_base. */
static inline uintptr_t fw_addr(uintptr_t a)
{
    __asm__ __volatile__("" : "+r"(a));
    return a;
}

static inline uint32_t rd32(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline uint16_t rd16(uintptr_t a) { return *(volatile uint16_t *)a; }
static inline uint8_t rd8(uintptr_t a) { return *(volatile uint8_t *)a; }

static void resolve_sink(sink *s)
{
    memset(s, 0, sizeof *s);
    for (int i = 0; i < 4; i++) {
        if (memcmp((const void *)(uintptr_t)k_ident_addr[i], k_ident[i], 16) != 0) {
            NBT_LOG("NBT_KEYBOARD_NATIVE_IDENTITY_FAILED\n");
            return;
        }
    }
    if (rd8(ADDR_SINGLETON_GUARD) == 0) return;
    uint32_t type = rd16(ADDR_TYPE_U16);
    s->type = type;
    if (type == 0 || rd32(ADDR_TYPE_TAG) != TYPE_TAG_VALUE) return;
    void *legacy = ((fn_void)fw_addr(ADDR_LEGACY_GETTER))();
    if (!legacy) return;
    if (rd32((uintptr_t)legacy + 0xC4) == 0) return;
    void *context = ((fn_this)fw_addr(ADDR_CONTEXT_GETTER))(legacy);
    if (!context) return;
    uint32_t vt = rd32((uintptr_t)context);
    if (vt == 0 || rd32(vt + 0x10) == 0) return;
    fn_this_int g4 = (fn_this_int)(uintptr_t)rd32(vt + 0x10);
    void *candidate = g4(context, 0x0E);
    if (!candidate) return;
    void *proc = ((fn_this)fw_addr(ADDR_PROC_GETTER))(context);
    if (!proc || proc != candidate) return;
    uint32_t pvt = rd32((uintptr_t)proc);
    if (pvt == 0 || rd32(pvt + 0x1C) == 0) return;
    s->context = context;
    s->proc = proc;
    s->getter4 = g4;
    s->post = (fn_post)(uintptr_t)rd32(pvt + 0x1C);
    if (rd16(ADDR_TYPE_U16) != type) return;
    s->ready = 1;
}

static int reject(uint32_t len, uint32_t key, uint32_t pressed, uint32_t repeat)
{
    NBT_LOG("NBT_KEYBOARD_PACKET_REJECTED length=%u key=%u pressed=%u repeat=%u\n", len, key, pressed, repeat);
    return -1;
}

int nbt_keyboard_packet(const uint8_t *pkt, uint32_t len)
{
    uint32_t key = len > 4 ? pkt[4] : 0;
    uint32_t pressed = len > 5 ? pkt[5] : 0;
    uint32_t repeat = len > 7 ? (((uint32_t)pkt[6] << 8) | pkt[7]) : 0;
    if (len != 8 || pkt[3] != 1 || pressed > 1) return reject(len, key, pressed, repeat);
    if (key == 0) {
        if (pressed != 0 || repeat != 0) return reject(len, key, pressed, repeat);
    } else if (key == 13 || key == 14) {
        if (pressed != 0 || repeat < 1 || repeat > 64) return reject(len, key, pressed, repeat);
    } else if (key >= 1 && key <= 12) {
        if (repeat != 0) return reject(len, key, pressed, repeat);
    } else {
        return reject(len, key, pressed, repeat);
    }

    sink s;
    resolve_sink(&s);
    uint8_t ack[8];
    memcpy(ack, pkt, 8);
    ack[2] = 0xFD;

    if (key == 0) {
        void *display = 0, *manager = 0, *handler = 0;
        uint32_t enabled = 0;
        if (s.ready) {
            display = s.getter4(s.context, 0x1F);
            manager = s.getter4(s.context, 0x25);
            if (display) enabled = rd8((uintptr_t)display + 0x31) != 0;
            if (manager) handler = (void *)(uintptr_t)rd32((uintptr_t)manager + 4);
        }
        uint32_t ready = (s.ready && enabled && handler) ? 1u : 0u;
        NBT_LOG("NBT_KEYBOARD_CAPABILITY ready=%u queue_ready=%u type=%u context=%p sink=%p post=%p display=%p display_enabled=%u input_manager=%p input_handler=%p\n",
                ready, (unsigned)s.ready, s.type, s.context, s.proc, (void *)s.post, display, enabled, manager, handler);
        ack[5] = (uint8_t)ready;
        return nbt_input_send_ack(ack, key);
    }

    if (!s.ready) {
        NBT_LOG("NBT_KEYBOARD_NATIVE_QUEUE_NOT_READY key=%u type=%u\n", key, s.type);
        return -1;
    }
#ifdef NBT_EXPERIMENTAL_NATIVE
    if (key == 7 && pressed) nbt_native_devices_request_selection(14);
#endif
    uint8_t *ev = (uint8_t *)((fn_void)fw_addr(ADDR_EVENT_FACTORY))();
    if (!ev) {
        NBT_LOG("NBT_KEYBOARD_FACTORY_FAILED key=%u\n", key);
        return -1;
    }
    uint32_t routing = rd32((uintptr_t)ev + 4);
    if ((routing >> 16) != s.type || rd32((uintptr_t)ev + 0x0C) != 0) {
        NBT_LOG("NBT_KEYBOARD_NEW_EVENT_INVALID key=%u routing=0x%x registered_type=%u\n", key, routing, s.type);
        return -1;
    }
    *(volatile uint32_t *)(ev + 0x10) = key;
    *(volatile uint8_t *)(ev + 0x14) = (uint8_t)pressed;
    *(volatile uint8_t *)(ev + 0x1C) = 0;
    if (key == 13 || key == 14) *(volatile uint32_t *)(ev + 0x18) = repeat;
    uint32_t logged_repeat = rd32((uintptr_t)ev + 0x18);
    unsigned char accepted = s.post(s.proc, ev);
    /* the event now belongs to the native queue: never touched again */
    if (!accepted) {
        NBT_LOG("NBT_KEYBOARD_NATIVE_POST_FAILED key=%u sink=%p type=%u\n", key, s.proc, s.type);
        return -1;
    }
    g_posted++;
    NBT_LOG("NBT_KEYBOARD_EVENT_POSTED number=%u key=%u pressed=%u repeat=%u type=%u sink=%p post=%p\n",
            g_posted, key, pressed, logged_repeat, s.type, s.proc, (void *)s.post);
    return nbt_input_send_ack(ack, key);
}
