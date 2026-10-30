/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): PPM frame publication - atomic write-through replace, one off-thread worker.
 */
#include "glh.h"
#include <stdio.h>
#include <stdlib.h>

#define PATH_LIMIT 4095

/* Converts bottom-up RGBA to a top-down P6 file and atomically replaces path. 1 on success. */
int glh_publish_sync(const uint8_t *rgba, int w, int h, const char *path)
{
    if (!path || !*path || w <= 0 || h <= 0) return 0;
    char header[64];
    int hl = snprintf(header, sizeof header, "P6\n%d %d\n255\n", w, h);
    size_t row = (size_t)w * 3, total = (size_t)hl + row * (size_t)h;
    uint8_t *file = (uint8_t *)malloc(total);
    if (!file) return 0;
    memcpy(file, header, (size_t)hl);
    uint8_t *dst = file + hl;
    for (int y = 0; y < h; y++) {
        const uint8_t *src = rgba + (size_t)(h - 1 - y) * (size_t)w * 4;
        for (int x = 0; x < w; x++) {
            dst[0] = src[0]; dst[1] = src[1]; dst[2] = src[2];
            dst += 3; src += 4;
        }
    }
    size_t plen = strlen(path);
    char *tmp = (char *)malloc(plen + 5);
    if (!tmp) { free(file); return 0; }
    memcpy(tmp, path, plen);
    memcpy(tmp + plen, ".tmp", 5);
    int ok = 0;
    HANDLE f = CreateFileA(tmp, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f != INVALID_HANDLE_VALUE) {
        DWORD put = 0;
        BOOL wr = WriteFile(f, file, (DWORD)total, &put, NULL) && put == total;
        BOOL cl = CloseHandle(f);
        if (wr && cl) ok = MoveFileExA(tmp, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
    }
    free(tmp);
    free(file);
    return ok;
}

/* ------------------------------------------------------------------ worker: at most one pending frame */
static struct {
    CRITICAL_SECTION lock;
    CONDITION_VARIABLE changed;
    HANDLE thread;
    uint8_t *buf;            /* frame owned by the worker */
    size_t cap;
    int w, h;
    char path[PATH_LIMIT + 1];
    int pending, busy, stop, ready;
} P;

static DWORD WINAPI publish_main(LPVOID arg)
{
    (void)arg;
    EnterCriticalSection(&P.lock);
    for (;;) {
        while (!P.pending && !P.stop) SleepConditionVariableCS(&P.changed, &P.lock, INFINITE);
        if (!P.pending) break;
        P.pending = 0;
        P.busy = 1;
        LeaveCriticalSection(&P.lock);
        glh_publish_sync(P.buf, P.w, P.h, P.path);
        EnterCriticalSection(&P.lock);
        P.busy = 0;
        WakeAllConditionVariable(&P.changed);
    }
    LeaveCriticalSection(&P.lock);
    return 0;
}

void glh_publish_init(void)
{
    InitializeCriticalSection(&P.lock);
    InitializeConditionVariable(&P.changed);
    P.thread = CreateThread(NULL, 0, publish_main, NULL, 0, NULL);
    P.ready = P.thread != NULL;
}

/* *pixels holds w*h*4 bytes read back on the GL thread. The buffer may be exchanged with the worker's. */
void glh_publish_async(uint8_t **pixels, int w, int h, const char *path)
{
    size_t need = (size_t)w * (size_t)h * 4;
    if (!P.ready || !path || strlen(path) > PATH_LIMIT) { glh_publish_sync(*pixels, w, h, path); return; }
    EnterCriticalSection(&P.lock);
    while (P.pending || P.busy) SleepConditionVariableCS(&P.changed, &P.lock, INFINITE);
    if (P.cap != need) {
        uint8_t *nb = (uint8_t *)realloc(P.buf, need);
        if (!nb) { LeaveCriticalSection(&P.lock); glh_publish_sync(*pixels, w, h, path); return; }
        P.buf = nb;
        P.cap = need;
    }
    /* hand the freshly read frame to the worker and take its old buffer back (same size) */
    uint8_t *mine = *pixels;
    *pixels = P.buf;
    P.buf = mine;
    P.w = w;
    P.h = h;
    memcpy(P.path, path, strlen(path) + 1);
    P.pending = 1;
    WakeAllConditionVariable(&P.changed);
    LeaveCriticalSection(&P.lock);
}

void glh_publish_shutdown(void)
{
    if (!P.ready) return;
    EnterCriticalSection(&P.lock);
    while (P.pending || P.busy) SleepConditionVariableCS(&P.changed, &P.lock, INFINITE);
    P.stop = 1;
    WakeAllConditionVariable(&P.changed);
    LeaveCriticalSection(&P.lock);
    WaitForSingleObject(P.thread, INFINITE);
    CloseHandle(P.thread);
    P.thread = NULL;
    P.ready = 0;
}
