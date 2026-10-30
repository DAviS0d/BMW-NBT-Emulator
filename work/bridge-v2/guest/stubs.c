/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): Annex A stubs, QNX slog exports and eglGetProcAddress.
 */
#include "nbt_guest.h"
#include "names.h"

/* ---------------------------------------------------------------- Annex A stubs */
/* Each stub reports itself once on fd 2, ignores its (cdecl, caller-popped) arguments and returns 0 in EAX. */
#define NBT_DEFINE_STUB(name)                                                   \
    static volatile int stub_seen_##name;                                       \
    NBT_API int name(void)                                                      \
    {                                                                           \
        if (__sync_lock_test_and_set(&stub_seen_##name, 1) == 0)                \
            nbt_fd2("glbridge: unsupported " #name "\n");                      \
        return 0;                                                               \
    }
NBT_STUB_NAMES(NBT_DEFINE_STUB)

/* ---------------------------------------------------------------- slog */
NBT_API int vslogf(int code, int severity, const char *fmt, va_list ap)
{
    (void)code; (void)severity;
    if (!fmt) return -1;
    char buf[1024];
    int n = vsnprintf(buf, sizeof buf, fmt, ap);
    if (n < 0) return -1;
    if (n > 1023) n = 1023;
    const char *p = buf;
    int left = n;
    while (left > 0) {
        int w = write(2, p, (size_t)left);
        if (w <= 0) return -1;
        p += w;
        left -= w;
    }
    if (n == 0 || buf[n - 1] != '\n') {
        if (write(2, "\n", 1) != 1) return -1;
    }
    return n;
}

NBT_API int slogf(int code, int severity, const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    int r = vslogf(code, severity, fmt, ap);
    va_end(ap);
    return r;
}

NBT_API int slog2f(void *buffer, uint16_t code, uint8_t severity, const char *fmt, ...) { (void)buffer; (void)code; (void)severity; (void)fmt; return 0; }
NBT_API int slog2c(void *buffer, uint16_t code, uint8_t severity, const char *text) { (void)buffer; (void)code; (void)severity; (void)text; return 0; }
NBT_API int slog2_register(const void *config, void **handles, uint32_t flags) { (void)config; (void)handles; (void)flags; return 0; }

/* ---------------------------------------------------------------- eglGetProcAddress */
/* Addresses only: the functions are declared with a neutral prototype in this translation unit. */
#define NBT_DECLARE(name) extern void name(void);
NBT_GL_NAMES(NBT_DECLARE)
NBT_EGL_PROC_NAMES(NBT_DECLARE)

typedef struct proc_entry { const char *name; void (*fn)(void); } proc_entry;

#define NBT_ENTRY(name) { #name, (void (*)(void))name },
static const proc_entry g_procs[] = {
    NBT_GL_NAMES(NBT_ENTRY)
    NBT_STUB_NAMES(NBT_ENTRY)
    NBT_EGL_PROC_NAMES(NBT_ENTRY)
};

NBT_API void *eglGetProcAddress(const char *name)
{
    if (name) {
        for (size_t i = 0; i < sizeof g_procs / sizeof g_procs[0]; i++)
            if (strcmp(g_procs[i].name, name) == 0) return (void *)g_procs[i].fn;
    }
    nbt_fd2("glbridge: unresolved EGL procedure: ");
    nbt_fd2(name ? name : "(null)");
    nbt_fd2("\n");
    return (void *)0;
}
