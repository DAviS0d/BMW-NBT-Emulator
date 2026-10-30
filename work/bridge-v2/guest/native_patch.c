#include "nbt_guest.h"
NBT_IMPORT int mprotect(void *, size_t, int);

/* QNX imagefs text pages cannot gain WRITE protection (EACCES). Make a
 * process-private anonymous copy at the same VA before changing pinned code.
 * This runs only from library constructors, before the original UI starts. */
int nbt_native_writable_page(uintptr_t address)
{
    void *page = (void *)(address & ~(uintptr_t)4095);
    if (mprotect(page, 4096, 0x700) == 0) return 0;
    void *copy = malloc(4096);
    if (!copy) return -1;
    memcpy(copy, page, 4096);
    void *replacement = mmap64(page, 4096, 0x700, 0x80012, -1, 0);
    if (replacement != page) {
        free(copy);
        NBT_LOG("NBT_NATIVE_PRIVATE_PAGE_FAILED address=%p errno=%d\n", page, nbt_errno());
        return -1;
    }
    memcpy(page, copy, 4096);
    free(copy);
    nbt_mb();
    NBT_LOG("NBT_NATIVE_PRIVATE_TEXT_PAGE address=%p\n", page);
    return 0;
}
