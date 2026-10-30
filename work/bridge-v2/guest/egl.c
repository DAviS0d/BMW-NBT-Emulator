/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): EGL 1.4 surface of the bridge (fixed handles, local answers, swap markers).
 */
#include "nbt_guest.h"
#include "gl_types.h"

#define ONE ((void *)1)

static volatile EGLint g_egl_error = 0x3000;
static volatile uint32_t g_frames;

static void set_error(EGLint e) { g_egl_error = e; }

static void surface_size(EGLint *w, EGLint *h)
{
    const char *sw = getenv("GLBRIDGE_W");
    const char *sh = getenv("GLBRIDGE_H");
    int iw = sw ? atoi(sw) : 0;
    int ih = sh ? atoi(sh) : 0;
    *w = iw > 0 ? iw : 800;
    *h = ih > 0 ? ih : 480;
}

NBT_API EGLDisplay eglGetDisplay(EGLNativeDisplayType d) { (void)d; return ONE; }
NBT_API EGLDisplay eglGetPlatformDisplay(EGLenum p, void *n, const EGLAttrib *a) { (void)p; (void)n; (void)a; return ONE; }

NBT_API EGLBoolean eglInitialize(EGLDisplay dpy, EGLint *major, EGLint *minor)
{
    (void)dpy;
    if (major) *major = 1;
    if (minor) *minor = 4;
    EGLint w, h;
    surface_size(&w, &h);
    nbt_send_simple(1, 2, (uint32_t)w, (uint32_t)h);
    return 1;
}

NBT_API EGLBoolean eglGetConfigs(EGLDisplay dpy, EGLConfig *configs, EGLint size, EGLint *num)
{
    (void)dpy;
    if (configs && size > 0) configs[0] = ONE;
    if (num) *num = 1;
    return 1;
}

NBT_API EGLBoolean eglChooseConfig(EGLDisplay dpy, const EGLint *attrs, EGLConfig *configs, EGLint size, EGLint *num)
{
    (void)attrs;
    return eglGetConfigs(dpy, configs, size, num);
}

NBT_API EGLBoolean eglGetConfigAttrib(EGLDisplay dpy, EGLConfig cfg, EGLint attr, EGLint *value)
{
    (void)dpy; (void)cfg;
    EGLint v = 0;
    switch (attr) {
    case 0x3021: case 0x3022: case 0x3023: case 0x3024: v = 8; break;
    case 0x3020: v = 32; break;
    case 0x3025: v = 24; break;
    case 0x3026: v = 8; break;
    case 0x3028: v = 1; break;
    case 0x302E: v = 1; break;
    case 0x302F: v = 0; break;
    case 0x3033: v = 5; break;
    case 0x3040: v = 0x44; break;
    case 0x3042: v = 0x44; break;
    case 0x303F: v = 0x308E; break;
    case 0x3027: v = 0x3038; break;
    default: v = 0; break;
    }
    if (value) *value = v;
    return 1;
}

NBT_API EGLSurface eglCreateWindowSurface(EGLDisplay dpy, EGLConfig cfg, EGLNativeWindowType win, const EGLint *attrs)
{
    (void)dpy; (void)cfg; (void)win; (void)attrs;
    set_error(0x300B);
    nbt_fd2("NBT native window not implemented\n");
    return (EGLSurface)0;
}

NBT_API EGLSurface eglCreatePbufferSurface(EGLDisplay dpy, EGLConfig cfg, const EGLint *attrs) { (void)dpy; (void)cfg; (void)attrs; return ONE; }
NBT_API EGLContext eglCreateContext(EGLDisplay dpy, EGLConfig cfg, EGLContext share, const EGLint *attrs) { (void)dpy; (void)cfg; (void)share; (void)attrs; return ONE; }

NBT_API EGLBoolean eglMakeCurrent(EGLDisplay dpy, EGLSurface d, EGLSurface r, EGLContext c)
{
    (void)dpy; (void)d; (void)r; (void)c;
    nbt_flush_if_ready();
    return 1;
}

NBT_API EGLBoolean eglQuerySurface(EGLDisplay dpy, EGLSurface surf, EGLint attr, EGLint *value)
{
    (void)dpy;
    EGLint w, h;
    surface_size(&w, &h);
    if ((uintptr_t)surf > 1) {
        uint32_t wh[2];
        memcpy(wh, surf, 8);
        w = (EGLint)wh[0] > 0 ? (EGLint)wh[0] : 800;
        h = (EGLint)wh[1] > 0 ? (EGLint)wh[1] : 480;
    }
    EGLint v = 0;
    if (attr == 0x3057) v = w;
    else if (attr == 0x3056) v = h;
    if (value) *value = v;
    return 1;
}

NBT_API EGLBoolean eglSwapBuffers(EGLDisplay dpy, EGLSurface surf)
{
    (void)dpy; (void)surf;
#ifdef NBT_EXPERIMENTAL_NATIVE
    nbt_sports_tick();
#endif
    nbt_send_simple(5, 0);
    uint32_t n = __sync_add_and_fetch(&g_frames, 1u);
    if (n <= 3 || n % 30 == 0) {
        if (n == 1)
            NBT_LOG("NBT_VFAST_PERF_CONFIG loops_per_sleep=65536 timeout_iterations=800000000 profile=WHPX_ONLY\n");
        uint64_t ns = 0;
        int rc = ClockTime(QNX_CLOCK_REALTIME, (const uint64_t *)0, &ns);
        NBT_LOG("NBT_VFAST_PERF_FRAME frame=%u qnx_realtime_ns=%llu clock_rc=%d\n", n, (unsigned long long)ns, rc);
        nbt_virtio_print_perf(n);
    }
    return 1;
}

NBT_API EGLBoolean eglSwapInterval(EGLDisplay dpy, EGLint i) { (void)dpy; (void)i; return 1; }

NBT_API EGLint eglGetError(void)
{
    EGLint e = g_egl_error;
    g_egl_error = 0x3000;
    return e;
}

NBT_API EGLBoolean eglTerminate(EGLDisplay dpy) { (void)dpy; nbt_flush_if_ready(); return 1; }
NBT_API EGLBoolean eglReleaseThread(void) { nbt_flush_if_ready(); return 1; }
NBT_API EGLBoolean eglWaitGL(void) { nbt_flush_if_ready(); return 1; }
NBT_API EGLBoolean eglWaitNative(EGLint engine) { (void)engine; nbt_flush_if_ready(); return 1; }
NBT_API EGLBoolean eglDestroySurface(EGLDisplay dpy, EGLSurface s) { (void)dpy; (void)s; nbt_flush_if_ready(); return 1; }
NBT_API EGLBoolean eglDestroyContext(EGLDisplay dpy, EGLContext c) { (void)dpy; (void)c; nbt_flush_if_ready(); return 1; }

NBT_API EGLBoolean eglBindAPI(EGLenum api)
{
    if (api == 0x30A0) return 1;
    set_error(0x300C);
    return 0;
}

NBT_API EGLenum eglQueryAPI(void) { return 0x30A0; }

NBT_API EGLBoolean eglQueryContext(EGLDisplay dpy, EGLContext ctx, EGLint attr, EGLint *value)
{
    if (!dpy || !ctx || !value) { set_error(0x3006); return 0; }
    switch (attr) {
    case 0x3028: *value = 1; return 1;
    case 0x3097: *value = 0x30A0; return 1;
    case 0x3098: *value = 2; return 1;
    case 0x3086: *value = 0x3084; return 1;
    default: set_error(0x3004); return 0;
    }
}

NBT_API EGLBoolean eglSurfaceAttrib(EGLDisplay dpy, EGLSurface surf, EGLint attr, EGLint value)
{
    if (!dpy || !surf) { set_error(0x300D); return 0; }
    if (attr == 0x3093 && value == 0x3095) return 1;
    set_error(0x3004);
    return 0;
}

NBT_API EGLBoolean eglWaitClient(void) { nbt_gl_finish_internal(); return 1; }
NBT_API EGLBoolean eglBindTexImage(EGLDisplay d, EGLSurface s, EGLint b) { (void)d; (void)s; (void)b; set_error(0x3009); return 0; }
NBT_API EGLBoolean eglReleaseTexImage(EGLDisplay d, EGLSurface s, EGLint b) { (void)d; (void)s; (void)b; set_error(0x3009); return 0; }
NBT_API EGLBoolean eglCopyBuffers(EGLDisplay d, EGLSurface s, EGLNativePixmapType p) { (void)d; (void)s; (void)p; set_error(0x300A); return 0; }

NBT_API EGLSurface eglCreatePixmapSurface(EGLDisplay d, EGLConfig c, EGLNativePixmapType p, const EGLint *a)
{
    (void)d; (void)c; (void)p; (void)a;
    set_error(0x300A);
    return (EGLSurface)0;
}

NBT_API EGLSurface eglCreatePbufferFromClientBuffer(EGLDisplay d, EGLenum t, EGLClientBuffer b, EGLConfig c, const EGLint *a)
{
    (void)d; (void)t; (void)b; (void)c; (void)a;
    set_error(0x3009);
    return (EGLSurface)0;
}

NBT_API const char *eglQueryString(EGLDisplay dpy, EGLint name)
{
    (void)dpy;
    if (name == 0x3055) return "EGL_KHR_image EGL_KHR_image_base EGL_NV_system_time ";
    return "glshim-fwd";
}

NBT_API EGLuint64NV eglGetSystemTimeFrequencyNV(void) { return 1000000000ull; }

NBT_API EGLuint64NV eglGetSystemTimeNV(void)
{
    uint64_t ns = 0;
    if (ClockTime(QNX_CLOCK_MONOTONIC, (const uint64_t *)0, &ns) == -1) abort();
    return ns;
}

NBT_API EGLDisplay eglGetCurrentDisplay(void) { return ONE; }
NBT_API EGLContext eglGetCurrentContext(void) { return ONE; }
NBT_API EGLSurface eglGetCurrentSurface(EGLint which) { (void)which; return ONE; }

NBT_API EGLImageKHR eglCreateImageKHR(EGLDisplay d, EGLContext c, EGLenum t, EGLClientBuffer b, const EGLint *a)
{
    (void)d; (void)c; (void)t; (void)b; (void)a;
    set_error(0x300C);
    return (EGLImageKHR)0;
}

NBT_API EGLBoolean eglDestroyImageKHR(EGLDisplay d, EGLImageKHR i) { (void)d; (void)i; set_error(0x300C); return 0; }

NBT_API void NvEglRegClientApi(unsigned api, void *unused) { (void)api; (void)unused; }
