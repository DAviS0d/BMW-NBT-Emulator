/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): ANGLE/EGL setup, per-client contexts, opcode execution and replies.
 */
#include "glh.h"
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>

#define NAME_LIMIT   (1u << 20)
#define MAX_CLIENTS  32
#define RECORD_LIMIT (64u * 1024u * 1024u)
#define CACHE_SLOTS  16

typedef void *(GL_APIENTRY *map_range_fn)(GLenum, GLintptr, GLsizeiptr, GLbitfield);
typedef GLboolean (GL_APIENTRY *unmap_fn)(GLenum);

typedef struct client {
    uint32_t pid;
    EGLContext ctx;
    EGLSurface surf;
    GLuint *names;            /* guest name -> GL object */
    uint8_t *shader_mode;     /* blend mode per guest shader name */
    uint8_t *prog_mode;       /* blend mode per guest program name */
    uint32_t *prog_frag;      /* fragment shader (guest name) attached to a program */
    uint32_t active_prog;     /* guest name of the program in use (for blend) */
    uint8_t *attr_copy[16];   /* client-side vertex data (op 128) */
} client;

typedef struct cache_entry {
    int used;
    uint32_t id;
    int w, h;
    client *owner;
    uint64_t last_use;
    uint8_t *pixels;
} cache_entry;

enum { RUN_ON = 0, END_BREAK = 1, END_SILENT = 2 };

static struct {
    glh_channel *ch;
    EGLDisplay dpy;
    EGLConfig cfg;
    int have_window, w, h;
    client initial;
    client *clients[MAX_CLIENTS];
    int nclients;
    client *cur;
    uint32_t cur_pid, req_pid;
    client *primary;
    uint32_t frames;
    uint8_t *readback;
    const char *frame_path;
    int dump_clients, trace;
    const char *shader_dir;
    FILE *capture;
    uint32_t shader_bins;
    map_range_fn map_range;
    unmap_fn unmap;
    cache_entry cache[CACHE_SLOTS];
    uint64_t tick;
    uint8_t *scratch;
    size_t scratch_cap;
    glh_dma dma;
    int dma_attached;
} R;

/* ------------------------------------------------------------------ fatal exits */
static void die(int code)
{
    if (R.dma_attached) glh_dma_signal_stop(&R.dma);
    fflush(stderr);
    exit(code);
}

static void *xcalloc(size_t n, size_t s)
{
    void *p = calloc(n, s);
    if (!p) die(1);
    return p;
}

static void client_tables(client *c)
{
    c->names = (GLuint *)xcalloc(NAME_LIMIT, sizeof(GLuint));
    c->shader_mode = (uint8_t *)xcalloc(NAME_LIMIT, 1);
    c->prog_mode = (uint8_t *)xcalloc(NAME_LIMIT, 1);
    c->prog_frag = (uint32_t *)xcalloc(NAME_LIMIT, sizeof(uint32_t));
}

static GLuint N(uint32_t x) { return x < NAME_LIMIT ? R.cur->names[x] : 0; }

static uint8_t *scratch(size_t n)
{
    if (n == 0) n = 1;
    if (n > R.scratch_cap) {
        uint8_t *p = (uint8_t *)realloc(R.scratch, n);
        if (!p) die(1);
        R.scratch = p;
        R.scratch_cap = n;
    }
    return R.scratch;
}

/* ------------------------------------------------------------------ window and frame publication */
static void ensure_window(int32_t w, int32_t h)
{
    if (R.have_window) return;
    if (w <= 0 || w > 8192) w = 800;
    if (h <= 0 || h > 8192) h = 480;
    R.dpy = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    EGLint n = 0;
    static const EGLint cfg_attr[] = {
        EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8,
        EGL_DEPTH_SIZE, 24, EGL_STENCIL_SIZE, 8, EGL_NONE
    };
    if (R.dpy == EGL_NO_DISPLAY || !eglInitialize(R.dpy, NULL, NULL) ||
        !eglChooseConfig(R.dpy, cfg_attr, &R.cfg, 1, &n) || n < 1) {
        glh_log("EGL initialization failed 0x%x", (unsigned)eglGetError());
        die(1);
    }
    const EGLint pb_attr[] = { EGL_WIDTH, w, EGL_HEIGHT, h, EGL_NONE };
    static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    R.initial.surf = eglCreatePbufferSurface(R.dpy, R.cfg, pb_attr);
    R.initial.ctx = R.initial.surf ? eglCreateContext(R.dpy, R.cfg, EGL_NO_CONTEXT, ctx_attr) : EGL_NO_CONTEXT;
    if (R.initial.surf == EGL_NO_SURFACE || R.initial.ctx == EGL_NO_CONTEXT ||
        !eglMakeCurrent(R.dpy, R.initial.surf, R.initial.surf, R.initial.ctx)) {
        glh_log("EGL context failed 0x%x", (unsigned)eglGetError());
        die(1);
    }
    R.w = w;
    R.h = h;
    R.have_window = 1;
    R.readback = (uint8_t *)malloc((size_t)w * (size_t)h * 4);
    if (!R.readback) die(1);
    glh_log("glhost: window %dx%d, GLES = %s | %s", w, h,
            (const char *)glGetString(GL_VERSION), (const char *)glGetString(GL_RENDERER));
    glViewport(0, 0, w, h);
    glClearColor(0.05f, 0.05f, 0.10f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT);
    glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, R.readback);
    glh_publish_async(&R.readback, w, h, R.frame_path);
    eglSwapBuffers(R.dpy, R.initial.surf);
}

static void select_client(void)
{
    if (R.req_pid == R.cur_pid) return;
    ensure_window(0, 0);
    client *c = NULL;
    for (int i = 0; i < R.nclients; i++)
        if (R.clients[i]->pid == R.req_pid) { c = R.clients[i]; break; }
    if (!c) {
        if (R.nclients >= MAX_CLIENTS) {
            glh_log("Too many graphics clients");
            die(1);
        }
        c = (client *)xcalloc(1, sizeof *c);
        c->pid = R.req_pid;
        static const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
        const EGLint pb_attr[] = { EGL_WIDTH, R.w, EGL_HEIGHT, R.h, EGL_NONE };
        c->ctx = eglCreateContext(R.dpy, R.cfg, EGL_NO_CONTEXT, ctx_attr);
        c->surf = eglCreatePbufferSurface(R.dpy, R.cfg, pb_attr);
        if (c->ctx == EGL_NO_CONTEXT || c->surf == EGL_NO_SURFACE) die(1);
        client_tables(c);
        R.clients[R.nclients++] = c;
    }
    if (!eglMakeCurrent(R.dpy, c->surf, c->surf, c->ctx)) die(1);
    R.cur = c;
    R.cur_pid = R.req_pid;
}

/* ------------------------------------------------------------------ replies */
static int reply(const void *p, size_t n) { return glh_channel_write(R.ch, p, n); }

/* ------------------------------------------------------------------ hidden-call helpers (section 5.9) */
static void check_shader(GLuint sh, const char *label)
{
    GLint ok = 0;
    glGetShaderiv(sh, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[1024];
        GLsizei n = 0;
        log[0] = 0;
        glGetShaderInfoLog(sh, sizeof log, &n, log);
        log[1023] = 0;
        glh_log("glhost: %s FAILED: %s", label, log);
    }
}

static void check_program(GLuint p)
{
    GLint ok = 0;
    glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) {
        char log[1024];
        GLsizei n = 0;
        log[0] = 0;
        glGetProgramInfoLog(p, sizeof log, &n, log);
        log[1023] = 0;
        glh_log("glhost: link FAILED: %s", log);
    }
}

typedef struct blend_save { int mode; GLboolean was; GLint v[6]; } blend_save;

static const GLenum k_blend[6][4] = {
    { 0, 0, 0, 0 },
    { GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA },
    { GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_ZERO, GL_ONE },
    { GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA },
    { GL_ONE, GL_ZERO, GL_ONE, GL_ZERO },
    { GL_ZERO, GL_ZERO, GL_ZERO, GL_ZERO },
};

static void blend_begin(blend_save *s)
{
    uint32_t p = R.cur->active_prog;
    s->mode = p < NAME_LIMIT ? R.cur->prog_mode[p] : 0;
    if (s->mode < 1 || s->mode > 5) { s->mode = 0; return; }
    static const GLenum q[6] = { GL_BLEND_SRC_RGB, GL_BLEND_DST_RGB, GL_BLEND_SRC_ALPHA, GL_BLEND_DST_ALPHA,
                                 GL_BLEND_EQUATION_RGB, GL_BLEND_EQUATION_ALPHA };
    s->was = glIsEnabled(GL_BLEND);
    for (int i = 0; i < 6; i++) { s->v[i] = 0; glGetIntegerv(q[i], &s->v[i]); }
    glEnable(GL_BLEND);
    glBlendEquationSeparate(GL_FUNC_ADD, GL_FUNC_ADD);
    const GLenum *m = k_blend[s->mode];
    glBlendFuncSeparate(m[0], m[1], m[2], m[3]);
}

static void blend_end(const blend_save *s)
{
    if (!s->mode) return;
    glBlendFuncSeparate((GLenum)s->v[0], (GLenum)s->v[1], (GLenum)s->v[2], (GLenum)s->v[3]);
    glBlendEquationSeparate((GLenum)s->v[4], (GLenum)s->v[5]);
    if (!s->was) glDisable(GL_BLEND);
}

static uint8_t *read_pixels_packed(int32_t x, int32_t y, int32_t w, int32_t h)
{
    size_t n = (size_t)w * (size_t)h * 4;
    uint8_t *buf = scratch(n);
    memset(buf, 0, n);
    GLint pack = 0;
    glGetIntegerv(GL_PACK_ALIGNMENT, &pack);
    glPixelStorei(GL_PACK_ALIGNMENT, 1);
    glReadPixels(x, y, w, h, GL_RGBA, GL_UNSIGNED_BYTE, buf);
    glPixelStorei(GL_PACK_ALIGNMENT, pack);
    return buf;
}

static int excluded_pname(uint32_t p)
{
    return p == 0x86A2 || p == 0x86A3 || p == 0x8DF8 || p == 0x8DF9;
}

static void name_copy(char *dst, const uint8_t *src, uint32_t n)
{
    if (n > 255) n = 255;
    memcpy(dst, src, n);
    dst[n] = 0;
}

static void gen_objects(const uint8_t *p, uint32_t kind)
{
    uint32_t n = rd_u32(p);
    for (uint32_t i = 0; i < n; i++) {
        uint32_t id = rd_u32(p + 4 + 4 * i);
        GLuint obj = 0;
        switch (kind) {
        case 0: glGenBuffers(1, &obj); break;
        case 1: glGenTextures(1, &obj); break;
        case 2: glGenFramebuffers(1, &obj); break;
        default: glGenRenderbuffers(1, &obj); break;
        }
        if (id < NAME_LIMIT) R.cur->names[id] = obj;
    }
}

static void write_diag_file(const char *name, const void *p, size_t n)
{
    FILE *f = fopen(name, "wb");
    if (!f) return;
    if (n) fwrite(p, 1, n, f);
    fclose(f);
}

static uint32_t index_width(uint32_t t) { return t == 0x1401 ? 1u : t == 0x1403 ? 2u : 4u; }

static uint32_t ebo_max_index(uint32_t count, uint32_t type, uint32_t offset)
{
    GLint size = 0;
    glGetBufferParameteriv(GL_ELEMENT_ARRAY_BUFFER, GL_BUFFER_SIZE, &size);
    int valid = type == 0x1401 || type == 0x1403 || type == 0x1405;
    if (!valid || count == 0) return 0xFFFFFFFFu;
    if (!R.map_range) R.map_range = (map_range_fn)(void *)eglGetProcAddress("glMapBufferRange");
    if (!R.unmap) R.unmap = (unmap_fn)(void *)eglGetProcAddress("glUnmapBuffer");
    if (!R.map_range || !R.unmap) return 0xFFFFFFFFu;
    uint64_t w = index_width(type), bytes = (uint64_t)count * w;
    if (size < 0 || (uint64_t)offset + bytes > (uint64_t)size) return 0xFFFFFFFFu;
    const uint8_t *m = (const uint8_t *)R.map_range(GL_ELEMENT_ARRAY_BUFFER, (GLintptr)offset, (GLsizeiptr)bytes, 1);
    if (!m) return 0xFFFFFFFFu;
    uint32_t mx = 0;
    for (uint32_t i = 0; i < count; i++) {
        uint32_t v;
        if (w == 1) v = m[i];
        else if (w == 2) v = (uint32_t)m[2 * i] | ((uint32_t)m[2 * i + 1] << 8);
        else v = rd_u32(m + 4 * i);
        if (v > mx) mx = v;
    }
    R.unmap(GL_ELEMENT_ARRAY_BUFFER);
    return mx;
}

/* ------------------------------------------------------------------ native frame cache (131-133) */
static void cache_store(uint32_t id, int w, int h, const uint8_t *px)
{
    cache_entry *slot = NULL;
    for (int i = 0; i < CACHE_SLOTS && !slot; i++)
        if (R.cache[i].used && R.cache[i].id == id) slot = &R.cache[i];
    for (int i = 0; i < CACHE_SLOTS && !slot; i++)
        if (!R.cache[i].used) slot = &R.cache[i];
    if (!slot) {
        slot = &R.cache[0];
        for (int i = 1; i < CACHE_SLOTS; i++)
            if (R.cache[i].last_use < slot->last_use) slot = &R.cache[i];
    }
    size_t n = (size_t)w * (size_t)h * 4;
    uint8_t *buf = (uint8_t *)realloc(slot->pixels, n);
    if (!buf) die(1);
    memcpy(buf, px, n);
    slot->pixels = buf;
    slot->used = 1;
    slot->id = id;
    slot->w = w;
    slot->h = h;
    slot->owner = R.cur;
    slot->last_use = ++R.tick;
}

/* ------------------------------------------------------------------ execution of one validated record */
static int execute(uint32_t op, const uint8_t *p, uint32_t L)
{
    client *c = R.cur;
    switch (op) {
    case 1: return RUN_ON;                     /* window handled before selection */
    case 2: glViewport(rd_i32(p), rd_i32(p + 4), rd_i32(p + 8), rd_i32(p + 12)); return RUN_ON;
    case 3: glClearColor(rd_f32(p), rd_f32(p + 4), rd_f32(p + 8), rd_f32(p + 12)); return RUN_ON;
    case 4: glClear(rd_u32(p)); return RUN_ON;
    case 5: {
        if (!R.have_window) return RUN_ON;
        int main_target = !R.primary || R.cur == R.primary;
        if (main_target || R.dump_clients) {
            glReadPixels(0, 0, R.w, R.h, GL_RGBA, GL_UNSIGNED_BYTE, R.readback);
            if (R.dump_clients) {
                char name[64];
                snprintf(name, sizeof name, "nbt-client-%u.ppm", R.cur_pid);
                glh_publish_sync(R.readback, R.w, R.h, name);
            }
            if (main_target) glh_publish_async(&R.readback, R.w, R.h, R.frame_path);
        }
        eglSwapBuffers(R.dpy, c->surf);
        uint32_t n = ++R.frames;
        if (n <= 3 || n % 120 == 1) glh_log("glhost: %u frames swapped", n);
        return RUN_ON;
    }
    case 6: glFinish(); return RUN_ON;
    case 7: {
        uint32_t id = rd_u32(p);
        GLuint sh = glCreateShader(rd_u32(p + 4));
        c->names[id] = sh;
        c->shader_mode[id] = 0;
        return RUN_ON;
    }
    case 8: {
        uint32_t id = rd_u32(p), n = rd_u32(p + 4);
        char fname[64];
        snprintf(fname, sizeof fname, "nbt-source-%u.glsl", id);
        write_diag_file(fname, p + 8, n);
        c->shader_mode[id] = 0;
        const GLchar *src = (const GLchar *)(p + 8);
        GLint len = (GLint)n;
        glShaderSource(N(id), 1, &src, &len);
        return RUN_ON;
    }
    case 9: { GLuint sh = N(rd_u32(p)); glCompileShader(sh); check_shader(sh, "compile"); return RUN_ON; }
    case 10: {
        uint32_t id = rd_u32(p);
        c->prog_mode[id] = 0;
        c->prog_frag[id] = 0;
        c->names[id] = glCreateProgram();
        return RUN_ON;
    }
    case 11: {
        uint32_t prog = rd_u32(p), sh = rd_u32(p + 4);
        GLint type = 0;
        glGetShaderiv(N(sh), GL_SHADER_TYPE, &type);
        if (type == GL_FRAGMENT_SHADER) c->prog_frag[prog] = sh;
        glAttachShader(N(prog), N(sh));
        return RUN_ON;
    }
    case 12: {
        uint32_t prog = rd_u32(p);
        GLuint pg = N(prog);
        glLinkProgram(pg);
        check_program(pg);
        uint32_t frag = c->prog_frag[prog];
        c->prog_mode[prog] = frag < NAME_LIMIT ? c->shader_mode[frag] : 0;
        return RUN_ON;
    }
    case 13: {
        uint32_t prog = rd_u32(p);
        GLuint pg = N(prog);
        glUseProgram(pg);
        GLint cur = 0;
        glGetIntegerv(GL_CURRENT_PROGRAM, &cur);
        if ((GLuint)cur == pg) c->active_prog = prog;
        return RUN_ON;
    }
    case 14: {
        char name[256];
        name_copy(name, p + 12, rd_u32(p + 8));
        glBindAttribLocation(N(rd_u32(p)), rd_u32(p + 4), name);
        return RUN_ON;
    }
    case 15: gen_objects(p, 0); return RUN_ON;
    case 16: glBindBuffer(rd_u32(p), N(rd_u32(p + 4))); return RUN_ON;
    case 17: {
        uint32_t size = rd_u32(p + 4);
        const void *data = (size > 0 && L >= 12 && (uint64_t)L - 12 >= size) ? p + 12 : NULL;
        glBufferData(rd_u32(p), (GLsizeiptr)size, data, rd_u32(p + 8));
        return RUN_ON;
    }
    case 18: {
        uint32_t size = rd_u32(p + 8);
        const void *data = (size > 0 && (uint64_t)L - 12 >= size) ? p + 12 : NULL;
        glBufferSubData(rd_u32(p), (GLintptr)rd_i32(p + 4), (GLsizeiptr)size, data);
        return RUN_ON;
    }
    case 19: {
        GLint ab = 0;
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &ab);
        if (ab == 0) {
            glh_log("glhost: vertex array lacks transferred buffer");
            return END_SILENT;
        }
        glVertexAttribPointer(rd_u32(p), rd_i32(p + 4), rd_u32(p + 8), rd_u32(p + 12) ? GL_TRUE : GL_FALSE,
                              rd_i32(p + 16), (const void *)(uintptr_t)rd_u32(p + 20));
        return RUN_ON;
    }
    case 20: glEnableVertexAttribArray(rd_u32(p)); return RUN_ON;
    case 21: glDisableVertexAttribArray(rd_u32(p)); return RUN_ON;
    case 22: glUniform1fv(rd_i32(p), rd_i32(p + 4), (const GLfloat *)(p + 8)); return RUN_ON;
    case 23: glUniform2fv(rd_i32(p), rd_i32(p + 4), (const GLfloat *)(p + 8)); return RUN_ON;
    case 24: glUniform3fv(rd_i32(p), rd_i32(p + 4), (const GLfloat *)(p + 8)); return RUN_ON;
    case 25: glUniform4fv(rd_i32(p), rd_i32(p + 4), (const GLfloat *)(p + 8)); return RUN_ON;
    case 26: glUniformMatrix2fv(rd_i32(p), rd_i32(p + 4), rd_u32(p + 8) ? GL_TRUE : GL_FALSE, (const GLfloat *)(p + 12)); return RUN_ON;
    case 27: glUniformMatrix3fv(rd_i32(p), rd_i32(p + 4), rd_u32(p + 8) ? GL_TRUE : GL_FALSE, (const GLfloat *)(p + 12)); return RUN_ON;
    case 28: glUniformMatrix4fv(rd_i32(p), rd_i32(p + 4), rd_u32(p + 8) ? GL_TRUE : GL_FALSE, (const GLfloat *)(p + 12)); return RUN_ON;
    case 29: glUniform1f(rd_i32(p), rd_f32(p + 4)); return RUN_ON;
    case 30: glUniform1i(rd_i32(p), rd_i32(p + 4)); return RUN_ON;
    case 31: {
        blend_save s;
        blend_begin(&s);
        glDrawArrays(rd_u32(p), rd_i32(p + 4), rd_i32(p + 8));
        blend_end(&s);
        return RUN_ON;
    }
    case 32: {
        blend_save s;
        blend_begin(&s);
        glDrawElements(rd_u32(p), rd_i32(p + 4), rd_u32(p + 8), (const void *)(uintptr_t)rd_u32(p + 12));
        blend_end(&s);
        return RUN_ON;
    }
    case 33: glEnable(rd_u32(p)); return RUN_ON;
    case 34: glDisable(rd_u32(p)); return RUN_ON;
    case 35: glBlendFunc(rd_u32(p), rd_u32(p + 4)); return RUN_ON;
    case 36: glDepthFunc(rd_u32(p)); return RUN_ON;
    case 37: glCullFace(rd_u32(p)); return RUN_ON;
    case 38: glFrontFace(rd_u32(p)); return RUN_ON;
    case 39: glDepthMask(rd_u32(p) ? GL_TRUE : GL_FALSE); return RUN_ON;
    case 40: glClearDepthf(rd_f32(p)); return RUN_ON;
    case 42: glLineWidth(rd_f32(p)); return RUN_ON;
    case 43: glPolygonOffset(rd_f32(p), rd_f32(p + 4)); return RUN_ON;
    case 50: gen_objects(p, 1); return RUN_ON;
    case 51: glBindTexture(rd_u32(p), N(rd_u32(p + 4))); return RUN_ON;
    case 52: case 56: {
        uint32_t s = rd_u32(p + 32);
        const void *data = (s > 0 && (uint64_t)L - 36 >= s) ? p + 36 : NULL;
        if (op == 52)
            glTexImage2D(rd_u32(p), rd_i32(p + 4), rd_i32(p + 8), rd_i32(p + 12), rd_i32(p + 16), rd_i32(p + 20),
                         rd_u32(p + 24), rd_u32(p + 28), data);
        else
            glTexSubImage2D(rd_u32(p), rd_i32(p + 4), rd_i32(p + 8), rd_i32(p + 12), rd_i32(p + 16), rd_i32(p + 20),
                            rd_u32(p + 24), rd_u32(p + 28), data);
        return RUN_ON;
    }
    case 53: glTexParameteri(rd_u32(p), rd_u32(p + 4), rd_i32(p + 8)); return RUN_ON;
    case 54: glActiveTexture(rd_u32(p)); return RUN_ON;
    case 55: glPixelStorei(rd_u32(p), rd_i32(p + 4)); return RUN_ON;
    case 57: glGenerateMipmap(rd_u32(p)); return RUN_ON;
    case 58: glTexParameterf(rd_u32(p), rd_u32(p + 4), rd_f32(p + 8)); return RUN_ON;
    case 60: glBindFramebuffer(rd_u32(p), N(rd_u32(p + 4))); return RUN_ON;
    case 61: glBindRenderbuffer(rd_u32(p), N(rd_u32(p + 4))); return RUN_ON;
    case 62: glFramebufferTexture2D(rd_u32(p), rd_u32(p + 4), rd_u32(p + 8), N(rd_u32(p + 12)), rd_i32(p + 16)); return RUN_ON;
    case 63: glRenderbufferStorage(rd_u32(p), rd_u32(p + 4), rd_i32(p + 8), rd_i32(p + 12)); return RUN_ON;
    case 64: glFramebufferRenderbuffer(rd_u32(p), rd_u32(p + 4), rd_u32(p + 8), N(rd_u32(p + 12))); return RUN_ON;
    case 65: glScissor(rd_i32(p), rd_i32(p + 4), rd_i32(p + 8), rd_i32(p + 12)); return RUN_ON;
    case 66: glColorMask((GLboolean)rd_u32(p), (GLboolean)rd_u32(p + 4), (GLboolean)rd_u32(p + 8), (GLboolean)rd_u32(p + 12)); return RUN_ON;
    case 67: glClearStencil(rd_i32(p)); return RUN_ON;
    case 68: glStencilMask(rd_u32(p)); return RUN_ON;
    case 69: glStencilFunc(rd_u32(p), rd_i32(p + 4), rd_u32(p + 8)); return RUN_ON;
    case 70: glStencilOp(rd_u32(p), rd_u32(p + 4), rd_u32(p + 8)); return RUN_ON;
    case 71: glBlendFuncSeparate(rd_u32(p), rd_u32(p + 4), rd_u32(p + 8), rd_u32(p + 12)); return RUN_ON;
    case 72: glBlendEquation(rd_u32(p)); return RUN_ON;
    case 73: glBlendEquationSeparate(rd_u32(p), rd_u32(p + 4)); return RUN_ON;
    case 75: glStencilMaskSeparate(rd_u32(p), rd_u32(p + 4)); return RUN_ON;
    case 76: glStencilFuncSeparate(rd_u32(p), rd_u32(p + 4), rd_i32(p + 8), rd_u32(p + 12)); return RUN_ON;
    case 77: glStencilOpSeparate(rd_u32(p), rd_u32(p + 4), rd_u32(p + 8), rd_u32(p + 12)); return RUN_ON;
    case 78: gen_objects(p, 2); return RUN_ON;
    case 79: gen_objects(p, 3); return RUN_ON;
    case 80: glUniform1iv(rd_i32(p), rd_i32(p + 4), (const GLint *)(p + 8)); return RUN_ON;
    case 81: glUniform2iv(rd_i32(p), rd_i32(p + 4), (const GLint *)(p + 8)); return RUN_ON;
    case 82: glUniform3iv(rd_i32(p), rd_i32(p + 4), (const GLint *)(p + 8)); return RUN_ON;
    case 83: glUniform4iv(rd_i32(p), rd_i32(p + 4), (const GLint *)(p + 8)); return RUN_ON;
    case 84: {
        GLfloat v[4] = { rd_f32(p + 4), rd_f32(p + 8), rd_f32(p + 12), rd_f32(p + 16) };
        glVertexAttrib4fv(rd_u32(p), v);
        return RUN_ON;
    }
    case 85: glDepthRangef(rd_f32(p), rd_f32(p + 4)); return RUN_ON;
    case 86: glBlendColor(rd_f32(p), rd_f32(p + 4), rd_f32(p + 8), rd_f32(p + 12)); return RUN_ON;
    case 87: glHint(rd_u32(p), rd_u32(p + 4)); return RUN_ON;
    case 100: case 101: {
        char name[256];
        name_copy(name, p + 8, rd_u32(p + 4));
        GLint r = op == 100 ? glGetAttribLocation(N(rd_u32(p)), name) : glGetUniformLocation(N(rd_u32(p)), name);
        if (reply(&r, 4)) glh_log("glhost: getter reply failed");
        return RUN_ON;
    }
    case 102: case 103: {
        GLint v = 0;
        if (op == 102) glGetShaderiv(N(rd_u32(p)), rd_u32(p + 4), &v);
        else glGetProgramiv(N(rd_u32(p)), rd_u32(p + 4), &v);
        return reply(&v, 4) ? END_SILENT : RUN_ON;
    }
    case 104: {
        GLint v[16] = { 0 };
        if (!excluded_pname(rd_u32(p))) glGetIntegerv(rd_u32(p), v);
        return reply(v, 64) ? END_SILENT : RUN_ON;
    }
    case 105: { GLenum e = glGetError(); uint32_t v = e; return reply(&v, 4) ? END_SILENT : RUN_ON; }
    case 106: {
        GLboolean v[16] = { 0 };
        if (!excluded_pname(rd_u32(p))) glGetBooleanv(rd_u32(p), v);
        return reply(v, 16) ? END_SILENT : RUN_ON;
    }
    case 107: {
        GLfloat v[16] = { 0 };
        if (!excluded_pname(rd_u32(p))) glGetFloatv(rd_u32(p), v);
        return reply(v, 64) ? END_SILENT : RUN_ON;
    }
    case 108: {
        GLint v[3] = { 0, 0, 0 };
        GLint range[2] = { 0, 0 }, prec = 0;
        glGetShaderPrecisionFormat(rd_u32(p), rd_u32(p + 4), range, &prec);
        v[0] = range[0]; v[1] = range[1]; v[2] = prec;
        return reply(v, 12) ? END_SILENT : RUN_ON;
    }
    case 109: { uint32_t v = glCheckFramebufferStatus(rd_u32(p)); return reply(&v, 4) ? END_SILENT : RUN_ON; }
    case 110: {
        uint32_t count = rd_u32(p), format = rd_u32(p + 4), length = rd_u32(p + 8);
        const uint8_t *ids = p + 12, *bin = p + 12 + 4 * (size_t)count;
        char fname[96];
        snprintf(fname, sizeof fname, "nbt-shader-%u-%x.bin", R.shader_bins++, format);
        write_diag_file(fname, bin, length);
        glh_log("shader binary %s count=%u size=%u", fname, count, length);
        uint64_t hash = glh_fnv1a64(bin, length);
        int blend = 0;
        char *glsl = NULL;
        if (count == 1 && R.shader_dir && glh_shader_cache_lookup(R.shader_dir, hash, length, &blend, &glsl)) {
            uint32_t sid = rd_u32(ids);
            c->shader_mode[sid] = (uint8_t)blend;
            GLuint sh = N(sid);
            const GLchar *src = glsl;
            glShaderSource(sh, 1, &src, NULL);
            glCompileShader(sh);
            check_shader(sh, "firmware source shader");
            free(glsl);
            return RUN_ON;
        }
        glh_log("UNSUPPORTED NVIDIA shader hash=%016llx", (unsigned long long)hash);
        die(4);
        return END_SILENT;
    }
    case 119: R.req_pid = rd_u32(p); return RUN_ON;
    case 120: case 131: {
        int32_t w = rd_i32(p + 8), h = rd_i32(p + 12);
        uint8_t *px = read_pixels_packed(rd_i32(p), rd_i32(p + 4), w, h);
        if (reply(px, (size_t)w * (size_t)h * 4)) return END_SILENT;
        if (op == 131) cache_store(rd_u32(p + 24), w, h, px);
        return RUN_ON;
    }
    case 122: case 126: case 127: case 134: case 135: case 136: case 137:
        glh_log("Unsupported video/encoder record %u", op);
        die(3);
        return END_SILENT;
    case 123: case 124: {
        uint32_t c4 = rd_u32(p + 8);
        uint8_t out[12 + 4096];
        GLchar name[4096];
        GLsizei length = 0;
        GLint size = 0;
        GLenum type = 0;
        memset(name, 0, sizeof name);
        if (op == 123) glGetActiveAttrib(N(rd_u32(p)), rd_u32(p + 4), (GLsizei)c4, &length, &size, &type, name);
        else glGetActiveUniform(N(rd_u32(p)), rd_u32(p + 4), (GLsizei)c4, &length, &size, &type, name);
        memcpy(out, &length, 4);
        memcpy(out + 4, &size, 4);
        memcpy(out + 8, &type, 4);
        memcpy(out + 12, name, c4);
        return reply(out, 12 + (size_t)c4) ? END_SILENT : RUN_ON;
    }
    case 125: R.primary = R.cur; return RUN_ON;
    case 128: {
        uint32_t idx = rd_u32(p), bytes = rd_u32(p + 20);
        uint8_t *copy = (uint8_t *)realloc(c->attr_copy[idx], bytes ? bytes : 1);
        if (!copy) die(1);
        memcpy(copy, p + 24, bytes);
        c->attr_copy[idx] = copy;
        GLint ab = 0;
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &ab);
        glBindBuffer(GL_ARRAY_BUFFER, 0);
        glVertexAttribPointer(idx, rd_i32(p + 4), rd_u32(p + 8), (GLboolean)rd_u32(p + 12), rd_i32(p + 16), copy);
        glBindBuffer(GL_ARRAY_BUFFER, (GLuint)ab);
        return RUN_ON;
    }
    case 129: {
        GLint eb = 0;
        glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING, &eb);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
        blend_save s;
        blend_begin(&s);
        glDrawElements(rd_u32(p), rd_i32(p + 4), rd_u32(p + 8), p + 16);
        blend_end(&s);
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, (GLuint)eb);
        return RUN_ON;
    }
    case 130: {
        uint32_t kind = rd_u32(p), n = rd_u32(p + 4);
        for (uint32_t i = 0; i < n; i++) {
            uint32_t id = rd_u32(p + 8 + 4 * i);
            if (id == 0 || id >= NAME_LIMIT || c->names[id] == 0) continue;
            GLuint obj = c->names[id];
            switch (kind) {
            case 0: glDeleteTextures(1, &obj); break;
            case 1: glDeleteBuffers(1, &obj); break;
            case 2: glDeleteFramebuffers(1, &obj); break;
            default: glDeleteRenderbuffers(1, &obj); break;
            }
            c->names[id] = 0;
        }
        return RUN_ON;
    }
    case 132: {
        uint32_t id = rd_u32(p);
        int32_t w = rd_i32(p + 4), h = rd_i32(p + 8);
        uint32_t hit = 0;
        for (int i = 0; i < CACHE_SLOTS; i++) {
            cache_entry *e = &R.cache[i];
            if (!e->used || e->id != id || e->w != w || e->h != h) continue;
            GLint ua = 0;
            glGetIntegerv(GL_UNPACK_ALIGNMENT, &ua);
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, e->pixels);
            glPixelStorei(GL_UNPACK_ALIGNMENT, ua);
            e->last_use = ++R.tick;
            hit = 1;
            break;
        }
        return reply(&hit, 4) ? END_SILENT : RUN_ON;
    }
    case 133: {
        uint32_t id = rd_u32(p);
        for (int i = 0; i < CACHE_SLOTS; i++) {
            cache_entry *e = &R.cache[i];
            if (e->used && e->id == id && e->owner == R.cur) {
                free(e->pixels);
                memset(e, 0, sizeof *e);
            }
        }
        return RUN_ON;
    }
    case 138: {
        uint32_t mx = ebo_max_index(rd_u32(p), rd_u32(p + 4), rd_u32(p + 8));
        return reply(&mx, 4) ? END_SILENT : RUN_ON;
    }
    case 139: {
        int32_t size = rd_i32(p + 24);
        if (!(L == 28 || 28ull + (uint32_t)size == L)) { glh_log("Invalid compressed texture record"); die(5); }
        glCompressedTexImage2D(rd_u32(p), rd_i32(p + 4), rd_u32(p + 8), rd_i32(p + 12), rd_i32(p + 16), rd_i32(p + 20),
                               size, L > 28 ? p + 28 : NULL);
        return RUN_ON;
    }
    case 140:
        if (L != 32) { glh_log("Invalid texture copy record"); die(5); }
        glCopyTexSubImage2D(rd_u32(p), rd_i32(p + 4), rd_i32(p + 8), rd_i32(p + 12), rd_i32(p + 16), rd_i32(p + 20),
                            rd_i32(p + 24), rd_i32(p + 28));
        return RUN_ON;
    case 141: {
        if (L != 8) { glh_log("Invalid vertex attribute query"); die(5); }
        GLint v[4] = { 0, 0, 0, 0 };
        glGetVertexAttribiv(rd_u32(p), rd_u32(p + 4), v);
        return reply(v, 16) ? END_SILENT : RUN_ON;
    }
    case 142: {
        if (L != 4) { glh_log("Invalid capability query"); die(5); }
        uint32_t v = glIsEnabled(rd_u32(p)) ? 1u : 0u;
        return reply(&v, 4) ? END_SILENT : RUN_ON;
    }
    case 143:
        if (L != 8) { glh_log("Invalid sample coverage record"); die(5); }
        glSampleCoverage(rd_f32(p), rd_u32(p + 4) ? GL_TRUE : GL_FALSE);
        return RUN_ON;
    case 144: {
        uint32_t ack = 0;
        const char *cfg = getenv("GLHOST_DMA_CONFIG");
        int ok = !R.dma_attached && cfg && *cfg &&
                 glh_dma_attach(&R.dma, p, cfg, glh_channel_cancel_flag(R.ch)) == 0;
        ack = ok ? 1u : 0u;
        if (glh_channel_write_base(R.ch, &ack, 4) != 0) {
            if (ok) glh_dma_close(&R.dma);
            return END_SILENT;
        }
        if (!ok) return END_SILENT;
        R.dma_attached = 1;
        glh_channel_use_dma(R.ch, &R.dma);
        return RUN_ON;
    }
    default:
        return RUN_ON;
    }
}

static int needs_client(uint32_t op)
{
    switch (op) {
    case 144: case 119: case 122: case 126: case 127: case 134: case 135: case 136: case 137: return 0;
    default: return 1;
    }
}

/* ------------------------------------------------------------------ session */
int glh_render_session(glh_channel *ch)
{
    memset(&R, 0, sizeof R);
    R.ch = ch;
    R.cur = &R.initial;
    client_tables(&R.initial);
    const char *fp = getenv("MHI2_GL_FRAME");
    R.frame_path = (fp && *fp) ? fp : "nbt-frame.ppm";
    const char *sd = getenv("MHI2_SHADER_CACHE");
    R.shader_dir = (sd && *sd) ? sd : NULL;
    R.trace = getenv("MHI2_GL_TRACE") != NULL;
    R.dump_clients = getenv("MHI2_GL_DUMP_CLIENTS") != NULL;
    const char *cap = getenv("MHI2_GL_CAPTURE");
    if (cap && *cap) R.capture = fopen(cap, "wb");
    glh_publish_init();

    uint8_t *payload = NULL;
    size_t payload_cap = 0;
    int end = RUN_ON;
    while (end == RUN_ON) {
        uint8_t hdr[8];
        if (!glh_channel_read_exact(ch, hdr, 8)) { end = END_BREAK; break; }
        uint32_t op = rd_u32(hdr), len = rd_u32(hdr + 4);
        if (len > RECORD_LIMIT) { end = END_BREAK; break; }
        size_t need = (size_t)len + 1;
        if (need > payload_cap) {
            uint8_t *nb = (uint8_t *)realloc(payload, need);
            if (!nb) { glh_log("glhost: OOM %u", len); end = END_BREAK; break; }
            payload = nb;
            payload_cap = need;
        }
        if (len && !glh_channel_read_exact(ch, payload, len)) { end = END_BREAK; break; }
        if (R.capture) {
            fwrite(hdr, 1, 8, R.capture);
            if (len) fwrite(payload, 1, len, R.capture);
            fflush(R.capture);
        }
        if (R.trace) glh_log("glhost op=%u len=%u", op, len);
        op = glh_normalize_op(op, len);
        if (!glh_validate(op, payload, len)) {
            glh_log("Invalid graphics record: op=%u len=%u", op, len);
            end = END_BREAK;
            break;
        }
        if (op == 1) ensure_window(rd_i32(payload), rd_i32(payload + 4));
        if (needs_client(op)) select_client();
        end = execute(op, payload, len);
    }
    free(payload);

    if (end == END_BREAK) glh_log("glhost: client disconnected after %u frames", R.frames);
    glh_publish_shutdown();
    if (R.dma_attached) {
        glh_dma_signal_stop(&R.dma);
        glh_log("GLHOST_DMA_COUNTS rx=%llu tx=%llu", (unsigned long long)R.dma.bytes_read,
                (unsigned long long)R.dma.bytes_written);
    }
    if (R.capture) fclose(R.capture);
    return 0;
}

void glh_render_release_dma(void)
{
    if (R.dma_attached) {
        glh_channel_use_dma(R.ch, NULL);
        glh_dma_close(&R.dma);
        R.dma_attached = 0;
    }
}
