/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): freestanding runtime helpers (mem*, fd 2 output, clock).
 */
#include "nbt_guest.h"

/* Statically provided helpers: hidden, so they never appear in the dynamic symbol table. */
__attribute__((visibility("hidden"))) void *memcpy(void *d, const void *s, size_t n)
{
    uint8_t *dp = (uint8_t *)d;
    const uint8_t *sp = (const uint8_t *)s;
    while (n >= 4) { uint32_t w; __builtin_memcpy(&w, sp, 4); __builtin_memcpy(dp, &w, 4); dp += 4; sp += 4; n -= 4; }
    while (n--) *dp++ = *sp++;
    return d;
}

__attribute__((visibility("hidden"))) void *memset(void *d, int c, size_t n)
{
    uint8_t *dp = (uint8_t *)d;
    uint32_t w = (uint8_t)c * 0x01010101u;
    while (n >= 4) { __builtin_memcpy(dp, &w, 4); dp += 4; n -= 4; }
    while (n--) *dp++ = (uint8_t)c;
    return d;
}

__attribute__((visibility("hidden"))) void *memmove(void *d, const void *s, size_t n)
{
    uint8_t *dp = (uint8_t *)d;
    const uint8_t *sp = (const uint8_t *)s;
    if (dp == sp || n == 0) return d;
    if (dp < sp || dp >= sp + n) {
        while (n--) *dp++ = *sp++;
    } else {
        dp += n; sp += n;
        while (n--) *--dp = *--sp;
    }
    return d;
}

__attribute__((visibility("hidden"))) int memcmp(const void *a, const void *b, size_t n)
{
    const uint8_t *x = (const uint8_t *)a, *y = (const uint8_t *)b;
    for (size_t i = 0; i < n; i++)
        if (x[i] != y[i]) return x[i] < y[i] ? -1 : 1;
    return 0;
}

void nbt_fd2n(const void *p, size_t n)
{
    const uint8_t *b = (const uint8_t *)p;
    while (n > 0) {
        int r = write(2, b, n);
        if (r <= 0) return;
        b += r;
        n -= (size_t)r;
    }
}

void nbt_fd2(const char *s)
{
    nbt_fd2n(s, strlen(s));
}

uint64_t nbt_monotonic_ns(void)
{
    uint64_t ns = 0;
    if (ClockTime(QNX_CLOCK_MONOTONIC, (const uint64_t *)0, &ns) == -1) return 0;
    return ns;
}
