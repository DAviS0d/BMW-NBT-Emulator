/* Experimental, version-bound native NBT external-device list integration.
 * Original HmiMain3D SHA256: 554b67d4d6317cfb1715d544874fae8ddd2c975be503c9e2514e2dc2f3a0d693.
 * No host-side overlay: labels use the original list/label object interfaces.
 * Build only into the separate experimental IFS with NBT_EXPERIMENTAL_NATIVE.
 */
#include "nbt_guest.h"

NBT_IMPORT int mprotect(void *address, size_t length, int protection);

#define DEV_PROT_RX 0x500
#define DEV_PROT_RWX 0x700
#define DEV_MAP_PRIVATE_ANON 0x80002
#define DEV_PAGE 4096u

typedef int (*init_fn)(void *, void *);
typedef void (*select_fn)(void *, uint32_t, uint32_t, uint32_t);
typedef void (*label_ctor_fn)(void *, const void *);
typedef void (*label_dtor_fn)(void *);
typedef int (*index_fn)(void *, uint32_t);
typedef void (*set_item_fn)(void *, const void *, int, int);
typedef void (*enable_fn)(void *, int, int);

static init_fn g_original_init;
static select_fn g_original_select;
static volatile uint32_t g_pending_selection;
static int g_devices_installed;
static inline uintptr_t device_native_addr(uintptr_t address)
{
    __asm__ __volatile__("" : "+r"(address));
    return address;
}

/* Read-only source representation of this firmware's 28-byte UTF16 string.
 * Native label ctor performs an owning copy; this source is never destroyed.
 * Layout verified from original string init/copy at0x0806017a/0x080601b4.
 */
typedef struct native_string_source {
    uint32_t allocator;
    union { uint16_t small[8]; const uint16_t *large; } storage;
    uint32_t length;
    uint32_t capacity;
} native_string_source;
_Static_assert(sizeof(native_string_source) == 28, "Expected original x86 UTF16 string layout");

static const uint16_t k_android_auto[] = {
    'A','n','d','r','o','i','d',' ','A','u','t','o',0
};
static const native_string_source k_android_label = {
    0, {.large = k_android_auto}, 12, 12
};
static const native_string_source k_carplay_label = {
    0, {.small = {'C','a','r','P','l','a','y',0}}, 7, 7
};
static const uint16_t k_bluetooth_text[] = {'B','l','u','e','t','o','o','t','h',' ','(','P','C',')',0};
static const native_string_source k_bluetooth_label = {0, {.large=k_bluetooth_text}, 14, 14};

static void set_native_label(void *list, uint32_t identifier, const native_string_source *text)
{
    uint32_t *vtable = *(uint32_t **)list;
    index_fn find_index = (index_fn)vtable[0x8c / 4];
    set_item_fn set_item = (set_item_fn)vtable[0x78 / 4];
    enable_fn enable = (enable_fn)vtable[0x7c / 4];
    int row = find_index(list, identifier);
    if (row < 0) {
        NBT_LOG("NBT_NATIVE_DEVICE_ROW_MISSING id=%u\n", identifier);
        return;
    }
    uint32_t label[6] = {0};
    ((label_ctor_fn)device_native_addr(0x080cd116))(label, text);
    set_item(list, label, row, 1);
    /* Original LegacyFW assertion identifies this method as setItemEnabled. */
    enable(list, row, 1);
    ((label_dtor_fn)device_native_addr(0x080cca5a))(label);
    NBT_LOG("NBT_NATIVE_DEVICE_ROW_READY id=%u row=%d\n", identifier, row);
}

static int devices_init_hook(void *controller, void *argument)
{
    int result = g_original_init(controller, argument);
    void *list = *(void **)((uint8_t *)controller + 0x7c);
    if (list) {
        set_native_label(list, 4, &k_bluetooth_label);
        set_native_label(list, 12, &k_android_label);
        set_native_label(list, 13, &k_carplay_label);
    }
    return result;
}

static void devices_select_hook(void *controller, uint32_t first, uint32_t second, uint32_t item)
{
    if (item == 4 || item == 12 || item == 13) {
        nbt_native_devices_request_selection(item);
        NBT_LOG("NBT_NATIVE_DEVICE_SELECTED id=%u\n", item);
        return;
    }
    g_original_select(controller, first, second, item);
}

uint32_t nbt_native_devices_take_selection(void)
{
    return __sync_lock_test_and_set(&g_pending_selection, 0);
}
void nbt_native_devices_request_selection(uint32_t identifier)
{
    __sync_lock_test_and_set(&g_pending_selection, identifier);
#ifdef NBT_STANDALONE_NATIVE
    nbt_native_mailbox_selection(identifier);
#endif
}

static void jump(uint8_t *destination, const void *target)
{
    destination[0] = 0xe9;
    uint32_t displacement = (uint32_t)(uintptr_t)target - (uint32_t)(uintptr_t)(destination + 5);
    memcpy(destination + 1, &displacement, 4);
}

int nbt_native_devices_install(void)
{
    if (g_devices_installed) return 0;
    const char *option = getenv("NBT_NATIVE_DEVICES");
    if (option && option[0] == '0') return 1;
    uint8_t *init = (uint8_t *)0x084572f8;
    uint8_t *selection = (uint8_t *)0x08453b96;
    static const uint8_t init_prefix[6] = {0x55,0x89,0xe5,0x57,0x56,0x53};
    static const uint8_t selection_prefix[7] = {0x55,0x89,0xe5,0x53,0x83,0xec,0x04};
    static const uint8_t label_prefix[6] = {0x55,0x89,0xe5,0x53,0x83,0xec};
    if (memcmp(init, init_prefix, sizeof(init_prefix)) ||
        memcmp(selection, selection_prefix, sizeof(selection_prefix)) ||
        memcmp((void *)0x080cd116, label_prefix, sizeof(label_prefix))) {
        NBT_LOG("NBT_NATIVE_DEVICES_UNSUPPORTED_HMI\n");
        return -1;
    }
    uint8_t *trampoline = mmap64(0, DEV_PAGE, DEV_PROT_RWX,
                                DEV_MAP_PRIVATE_ANON, QNX_NOFD, 0);
    if (trampoline == (void *)-1) {
        NBT_LOG("NBT_NATIVE_DEVICES_MMAP_FAILED errno=%d\n", nbt_errno());
        return -2;
    }
    memcpy(trampoline, init, sizeof(init_prefix));
    jump(trampoline + sizeof(init_prefix), init + sizeof(init_prefix));
    memcpy(trampoline + 32, selection, sizeof(selection_prefix));
    jump(trampoline + 32 + sizeof(selection_prefix), selection + sizeof(selection_prefix));
    if (mprotect(trampoline, DEV_PAGE, DEV_PROT_RX)) {
        NBT_LOG("NBT_NATIVE_DEVICES_TRAMPOLINE_PROTECT_FAILED errno=%d\n", nbt_errno());
        return -3;
    }
    void *init_page = (void *)((uintptr_t)init & ~(uintptr_t)(DEV_PAGE - 1));
    void *selection_page = (void *)((uintptr_t)selection & ~(uintptr_t)(DEV_PAGE - 1));
    if (nbt_native_writable_page((uintptr_t)init_page)) return -4;
    if (nbt_native_writable_page((uintptr_t)selection_page)) {
        mprotect(init_page, DEV_PAGE, DEV_PROT_RX);
        return -5;
    }
    g_original_init = (init_fn)trampoline;
    g_original_select = (select_fn)(trampoline + 32);
    jump(init, devices_init_hook);
    init[5] = 0x90;
    jump(selection, devices_select_hook);
    selection[5] = selection[6] = 0x90;
    nbt_mb();
    mprotect(init_page, DEV_PAGE, DEV_PROT_RX);
    mprotect(selection_page, DEV_PAGE, DEV_PROT_RX);
    g_devices_installed = 1;
    NBT_LOG("NBT_NATIVE_DEVICES_INSTALLED component=27224 android=12 carplay=13\n");
    return 0;
}

#ifdef NBT_EXPERIMENTAL_NATIVE
__attribute__((constructor)) static void native_devices_constructor(void)
{
    nbt_native_devices_install();
}
#endif
