/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): stderr logging - every line is written in one call and flushed.
 */
#include "glh.h"
#include <stdio.h>
#include <stdarg.h>

static CRITICAL_SECTION g_log_lock;
static volatile LONG g_log_ready;

void glh_log_init(void)
{
    if (InterlockedCompareExchange(&g_log_ready, 1, 0) == 0) {
        InitializeCriticalSection(&g_log_lock);
        setvbuf(stderr, NULL, _IONBF, 0);
        InterlockedExchange(&g_log_ready, 2);
    }
    while (g_log_ready != 2) Sleep(0);
}

void glh_log(const char *fmt, ...)
{
    char buf[2048];
    va_list ap;
    if (g_log_ready != 2) glh_log_init();
    va_start(ap, fmt);
    int n = vsnprintf(buf, sizeof buf - 1, fmt, ap);
    va_end(ap);
    if (n < 0) return;
    if (n > (int)sizeof buf - 2) n = (int)sizeof buf - 2;
    buf[n++] = '\n';
    EnterCriticalSection(&g_log_lock);
    fwrite(buf, 1, (size_t)n, stderr);
    fflush(stderr);
    LeaveCriticalSection(&g_log_lock);
}
