/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): idle policy - spin < 3 ms after activity, then ~1 ms high-resolution timer waits.
 */
#include "glh.h"

#ifndef CREATE_WAITABLE_TIMER_HIGH_RESOLUTION
#define CREATE_WAITABLE_TIMER_HIGH_RESOLUTION 0x00000002
#endif

static LONGLONG g_qpf;

void glh_idle_init(glh_idle *w)
{
    LARGE_INTEGER f;
    if (!g_qpf) { QueryPerformanceFrequency(&f); g_qpf = f.QuadPart ? f.QuadPart : 1; }
    QueryPerformanceCounter(&w->last_activity);
    w->timer = NULL;
    w->timer_tried = 0;
}

void glh_idle_touch(glh_idle *w)
{
    QueryPerformanceCounter(&w->last_activity);
}

void glh_idle_wait(glh_idle *w)
{
    LARGE_INTEGER now;
    QueryPerformanceCounter(&now);
    if ((now.QuadPart - w->last_activity.QuadPart) * 1000 < 3 * g_qpf) {
        YieldProcessor();
        return;
    }
    if (!w->timer_tried) {
        w->timer_tried = 1;
        w->timer = CreateWaitableTimerExW(NULL, NULL, CREATE_WAITABLE_TIMER_HIGH_RESOLUTION, TIMER_ALL_ACCESS);
    }
    if (w->timer) {
        LARGE_INTEGER due;
        due.QuadPart = -10000;              /* relative 1 ms in 100 ns units */
        if (SetWaitableTimer(w->timer, &due, 0, NULL, NULL, FALSE)) {
            WaitForSingleObject(w->timer, INFINITE);
            return;
        }
    }
    Sleep(1);
}

void glh_idle_close(glh_idle *w)
{
    if (w->timer) CloseHandle(w->timer);
    w->timer = NULL;
}
