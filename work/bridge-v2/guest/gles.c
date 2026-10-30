/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): GLES 2.0 entry points serialised to the renderer (section 2.6/2.8/2.10).
 */
#include "nbt_guest.h"
#include "gl_types.h"

#define MiB16 (16u * 1024u * 1024u)

static uint32_t f2u(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }

/* ======================================================================== simple state */
NBT_API void glViewport(GLint x, GLint y, GLsizei w, GLsizei h) { nbt_send_simple(2, 4, x, y, w, h); }
NBT_API void glClearColor(GLclampf r, GLclampf g, GLclampf b, GLclampf a) { nbt_send_simple(3, 4, f2u(r), f2u(g), f2u(b), f2u(a)); }
NBT_API void glClear(GLbitfield m) { nbt_send_simple(4, 1, m); }
void nbt_gl_finish_internal(void) { nbt_send_simple(6, 0); }
NBT_API void glFinish(void) { nbt_send_simple(6, 0); }
NBT_API void glFlush(void) { nbt_send_simple(6, 0); }
NBT_API void glCompileShader(GLuint s) { nbt_send_simple(9, 1, s); }
NBT_API void glAttachShader(GLuint p, GLuint s) { nbt_send_simple(11, 2, p, s); }
NBT_API void glLinkProgram(GLuint p) { nbt_send_simple(12, 1, p); }
NBT_API void glUseProgram(GLuint p) { nbt_send_simple(13, 1, p); }
NBT_API void glUniform1f(GLint l, GLfloat v) { nbt_send_simple(29, 2, l, f2u(v)); }
NBT_API void glUniform1i(GLint l, GLint v) { nbt_send_simple(30, 2, l, v); }
NBT_API void glEnable(GLenum c) { nbt_send_simple(33, 1, c); }
NBT_API void glDisable(GLenum c) { nbt_send_simple(34, 1, c); }
NBT_API void glBlendFunc(GLenum s, GLenum d) { nbt_send_simple(35, 2, s, d); }
NBT_API void glDepthFunc(GLenum f) { nbt_send_simple(36, 1, f); }
NBT_API void glCullFace(GLenum m) { nbt_send_simple(37, 1, m); }
NBT_API void glFrontFace(GLenum m) { nbt_send_simple(38, 1, m); }
NBT_API void glDepthMask(GLboolean f) { nbt_send_simple(39, 1, (uint32_t)f); }
NBT_API void glClearDepthf(GLclampf d) { nbt_send_simple(40, 1, f2u(d)); }
NBT_API void glLineWidth(GLfloat w) { nbt_send_simple(42, 1, f2u(w)); }
NBT_API void glPolygonOffset(GLfloat f, GLfloat u) { nbt_send_simple(43, 2, f2u(f), f2u(u)); }
NBT_API void glBindTexture(GLenum t, GLuint id) { nbt_send_simple(51, 2, t, id); }
NBT_API void glTexParameteri(GLenum t, GLenum p, GLint v) { nbt_send_simple(53, 3, t, p, v); }
NBT_API void glActiveTexture(GLenum t) { nbt_send_simple(54, 1, t); }
NBT_API void glPixelStorei(GLenum p, GLint v) { nbt_send_simple(55, 2, p, v); }
NBT_API void glGenerateMipmap(GLenum t) { nbt_send_simple(57, 1, t); }
NBT_API void glTexParameterf(GLenum t, GLenum p, GLfloat v) { nbt_send_simple(58, 3, t, p, f2u(v)); }
NBT_API void glBindFramebuffer(GLenum t, GLuint id) { nbt_send_simple(60, 2, t, id); }
NBT_API void glBindRenderbuffer(GLenum t, GLuint id) { nbt_send_simple(61, 2, t, id); }
NBT_API void glFramebufferTexture2D(GLenum t, GLenum a, GLenum tt, GLuint id, GLint l) { nbt_send_simple(62, 5, t, a, tt, id, l); }
NBT_API void glRenderbufferStorage(GLenum t, GLenum f, GLsizei w, GLsizei h) { nbt_send_simple(63, 4, t, f, w, h); }
NBT_API void glFramebufferRenderbuffer(GLenum t, GLenum a, GLenum rt, GLuint id) { nbt_send_simple(64, 4, t, a, rt, id); }
NBT_API void glScissor(GLint x, GLint y, GLsizei w, GLsizei h) { nbt_send_simple(65, 4, x, y, w, h); }
NBT_API void glColorMask(GLboolean r, GLboolean g, GLboolean b, GLboolean a) { nbt_send_simple(66, 4, (uint32_t)r, (uint32_t)g, (uint32_t)b, (uint32_t)a); }
NBT_API void glClearStencil(GLint s) { nbt_send_simple(67, 1, s); }
NBT_API void glStencilMask(GLuint m) { nbt_send_simple(68, 1, m); }
NBT_API void glStencilFunc(GLenum f, GLint r, GLuint m) { nbt_send_simple(69, 3, f, r, m); }
NBT_API void glStencilOp(GLenum a, GLenum b, GLenum c) { nbt_send_simple(70, 3, a, b, c); }
NBT_API void glBlendFuncSeparate(GLenum a, GLenum b, GLenum c, GLenum d) { nbt_send_simple(71, 4, a, b, c, d); }
NBT_API void glBlendEquation(GLenum m) { nbt_send_simple(72, 1, m); }
NBT_API void glBlendEquationSeparate(GLenum a, GLenum b) { nbt_send_simple(73, 2, a, b); }
NBT_API void glStencilMaskSeparate(GLenum f, GLuint m) { nbt_send_simple(75, 2, f, m); }
NBT_API void glStencilFuncSeparate(GLenum f, GLenum fn, GLint r, GLuint m) { nbt_send_simple(76, 4, f, fn, r, m); }
NBT_API void glStencilOpSeparate(GLenum f, GLenum a, GLenum b, GLenum c) { nbt_send_simple(77, 4, f, a, b, c); }
NBT_API void glDepthRangef(GLclampf n, GLclampf f) { nbt_send_simple(85, 2, f2u(n), f2u(f)); }
NBT_API void glBlendColor(GLclampf r, GLclampf g, GLclampf b, GLclampf a) { nbt_send_simple(86, 4, f2u(r), f2u(g), f2u(b), f2u(a)); }
NBT_API void glHint(GLenum t, GLenum m) { nbt_send_simple(87, 2, t, m); }
NBT_API void glCopyTexSubImage2D(GLenum t, GLint l, GLint xo, GLint yo, GLint x, GLint y, GLsizei w, GLsizei h) { nbt_send_simple(140, 8, t, l, xo, yo, x, y, w, h); }
NBT_API void glSampleCoverage(GLclampf v, GLboolean inv) { nbt_send_simple(143, 2, f2u(v), inv ? 1u : 0u); }

/* ======================================================================== objects */
NBT_API GLuint glCreateShader(GLenum type)
{
    uint32_t id = nbt_new_name();
    nbt_send_simple(7, 2, id, type);
    return id;
}

NBT_API GLuint glCreateProgram(void)
{
    uint32_t id = nbt_new_name();
    nbt_send_simple(10, 1, id);
    return id;
}

static void gen_names(uint32_t op, GLsizei n, GLuint *ids)
{
    if (!ids || n < 0) return;
    if ((uint32_t)n > (NBT_MAX_PAYLOAD - 4) / 4) abort();
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, op, 4u + 4u * (uint32_t)n);
    nbt_rec_i32(t, n);
    for (GLsizei i = 0; i < n; i++) {
        ids[i] = nbt_new_name();
        nbt_rec_u32(t, ids[i]);
    }
    nbt_rec_send(t);
}

NBT_API void glGenBuffers(GLsizei n, GLuint *ids) { gen_names(15, n, ids); }
NBT_API void glGenTextures(GLsizei n, GLuint *ids) { gen_names(50, n, ids); }
NBT_API void glGenFramebuffers(GLsizei n, GLuint *ids) { gen_names(78, n, ids); }
NBT_API void glGenRenderbuffers(GLsizei n, GLuint *ids) { gen_names(79, n, ids); }

static void delete_names(uint32_t kind, GLsizei n, const GLuint *ids)
{
    if (n <= 0 || !ids) return;
    if ((uint32_t)n > (NBT_MAX_PAYLOAD - 8) / 4) abort();
    nbt_thread *t = nbt_self();
    if (kind == 1) {
        for (GLsizei i = 0; i < n; i++) {
            uint32_t id = ids[i];
            if (id == 0) continue;
            if (t->array_buf == id) t->array_buf = 0;
            if (t->element_buf == id) t->element_buf = 0;
            for (int a = 0; a < NBT_MAX_ATTR; a++)
                if (t->attr[a].buffer == id) { t->attr[a].buffer = 0; t->attr[a].ptr = (const void *)0; }
        }
    }
    nbt_rec_begin(t, 130, 8u + 4u * (uint32_t)n);
    nbt_rec_u32(t, kind);
    nbt_rec_i32(t, n);
    nbt_rec_bytes(t, ids, 4u * (uint32_t)n);
    nbt_rec_send(t);
}

NBT_API void glDeleteTextures(GLsizei n, const GLuint *ids) { delete_names(0, n, ids); }
NBT_API void glDeleteBuffers(GLsizei n, const GLuint *ids) { delete_names(1, n, ids); }
NBT_API void glDeleteFramebuffers(GLsizei n, const GLuint *ids) { delete_names(2, n, ids); }
NBT_API void glDeleteRenderbuffers(GLsizei n, const GLuint *ids) { delete_names(3, n, ids); }

NBT_API void glShaderSource(GLuint sh, GLsizei count, const GLchar *const *str, const GLint *len)
{
    uint32_t total = 0;
    if (count < 0 || !str) count = 0;
    for (GLsizei i = 0; i < count; i++) {
        uint32_t l = (len && len[i] >= 0) ? (uint32_t)len[i] : (str[i] ? (uint32_t)strlen(str[i]) : 0u);
        if (!str[i]) l = 0;
        total += l;
        if (total > NBT_MAX_PAYLOAD) abort();
    }
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 8, 8u + total);
    nbt_rec_u32(t, sh);
    nbt_rec_u32(t, total);
    for (GLsizei i = 0; i < count; i++) {
        if (!str[i]) continue;
        uint32_t l = (len && len[i] >= 0) ? (uint32_t)len[i] : (uint32_t)strlen(str[i]);
        nbt_rec_bytes(t, str[i], l);
    }
    nbt_rec_send(t);
}

static void send_named(uint32_t op, uint32_t a, uint32_t b, int with_b, const char *name)
{
    uint32_t n = name ? (uint32_t)strlen(name) : 0u;
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, op, (with_b ? 12u : 8u) + n);
    nbt_rec_u32(t, a);
    if (with_b) nbt_rec_u32(t, b);
    nbt_rec_u32(t, n);
    nbt_rec_bytes(t, name, n);
    nbt_rec_send(t);
}

NBT_API void glBindAttribLocation(GLuint p, GLuint idx, const GLchar *name) { send_named(14, p, idx, 1, name); }

/* ======================================================================== buffers */
NBT_API void glBindBuffer(GLenum target, GLuint id)
{
    nbt_thread *t = nbt_self();
    if (target == 0x8892) t->array_buf = id;
    else if (target == 0x8893) t->element_buf = id;
    nbt_send_simple(16, 2, target, id);
}

NBT_API void glBufferData(GLenum target, GLsizeiptr size, const void *data, GLenum usage)
{
    uint32_t s = size < 0 ? 0u : (uint32_t)size;
    uint32_t body = data ? s : 0u;
    if (body > NBT_MAX_PAYLOAD - 12) abort();
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 17, 12u + body);
    nbt_rec_u32(t, target);
    nbt_rec_u32(t, s);
    nbt_rec_u32(t, usage);
    if (body) nbt_rec_bytes(t, data, body);
    nbt_rec_send(t);
}

NBT_API void glBufferSubData(GLenum target, GLintptr off, GLsizeiptr size, const void *data)
{
    uint32_t s = size < 0 ? 0u : (uint32_t)size;
    uint32_t body = data ? s : 0u;
    if (body > NBT_MAX_PAYLOAD - 12) abort();
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 18, 12u + body);
    nbt_rec_u32(t, target);
    nbt_rec_u32(t, (uint32_t)off);
    nbt_rec_u32(t, s);
    if (body) nbt_rec_bytes(t, data, body);
    nbt_rec_send(t);
}

/* ======================================================================== uniforms */
static void uniform_vec(uint32_t op, GLint loc, GLsizei count, const void *v, uint32_t k)
{
    if (count < 0 || (!v && count > 0)) return;
    uint64_t bytes = (uint64_t)(uint32_t)count * k * 4u;
    if (bytes > NBT_MAX_PAYLOAD - 8) abort();
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, op, 8u + (uint32_t)bytes);
    nbt_rec_i32(t, loc);
    nbt_rec_i32(t, count);
    nbt_rec_bytes(t, v, (uint32_t)bytes);
    nbt_rec_send(t);
}

NBT_API void glUniform1fv(GLint l, GLsizei c, const GLfloat *v) { uniform_vec(22, l, c, v, 1); }
NBT_API void glUniform2fv(GLint l, GLsizei c, const GLfloat *v) { uniform_vec(23, l, c, v, 2); }
NBT_API void glUniform3fv(GLint l, GLsizei c, const GLfloat *v) { uniform_vec(24, l, c, v, 3); }
NBT_API void glUniform4fv(GLint l, GLsizei c, const GLfloat *v) { uniform_vec(25, l, c, v, 4); }
NBT_API void glUniform2f(GLint l, GLfloat a, GLfloat b) { GLfloat v[2] = { a, b }; uniform_vec(23, l, 1, v, 2); }
NBT_API void glUniform3f(GLint l, GLfloat a, GLfloat b, GLfloat c) { GLfloat v[3] = { a, b, c }; uniform_vec(24, l, 1, v, 3); }
NBT_API void glUniform4f(GLint l, GLfloat a, GLfloat b, GLfloat c, GLfloat d) { GLfloat v[4] = { a, b, c, d }; uniform_vec(25, l, 1, v, 4); }
NBT_API void glUniform1iv(GLint l, GLsizei c, const GLint *v) { uniform_vec(80, l, c, v, 1); }
NBT_API void glUniform2iv(GLint l, GLsizei c, const GLint *v) { uniform_vec(81, l, c, v, 2); }
NBT_API void glUniform3iv(GLint l, GLsizei c, const GLint *v) { uniform_vec(82, l, c, v, 3); }
NBT_API void glUniform4iv(GLint l, GLsizei c, const GLint *v) { uniform_vec(83, l, c, v, 4); }
NBT_API void glUniform2i(GLint l, GLint a, GLint b) { GLint v[2] = { a, b }; uniform_vec(81, l, 1, v, 2); }
NBT_API void glUniform3i(GLint l, GLint a, GLint b, GLint c) { GLint v[3] = { a, b, c }; uniform_vec(82, l, 1, v, 3); }
NBT_API void glUniform4i(GLint l, GLint a, GLint b, GLint c, GLint d) { GLint v[4] = { a, b, c, d }; uniform_vec(83, l, 1, v, 4); }

static void uniform_mat(uint32_t op, GLint loc, GLsizei count, GLboolean tr, const GLfloat *v, uint32_t k)
{
    if (count < 0 || (!v && count > 0)) return;
    uint64_t bytes = (uint64_t)(uint32_t)count * k * k * 4u;
    if (bytes > NBT_MAX_PAYLOAD - 12) abort();
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, op, 12u + (uint32_t)bytes);
    nbt_rec_i32(t, loc);
    nbt_rec_i32(t, count);
    nbt_rec_u32(t, (uint32_t)tr);
    nbt_rec_bytes(t, v, (uint32_t)bytes);
    nbt_rec_send(t);
}

NBT_API void glUniformMatrix2fv(GLint l, GLsizei c, GLboolean tr, const GLfloat *v) { uniform_mat(26, l, c, tr, v, 2); }
NBT_API void glUniformMatrix3fv(GLint l, GLsizei c, GLboolean tr, const GLfloat *v) { uniform_mat(27, l, c, tr, v, 3); }
NBT_API void glUniformMatrix4fv(GLint l, GLsizei c, GLboolean tr, const GLfloat *v) { uniform_mat(28, l, c, tr, v, 4); }

/* ======================================================================== generic vertex attributes */
static void vattr(GLuint i, float x, float y, float z, float w) { nbt_send_simple(84, 5, i, f2u(x), f2u(y), f2u(z), f2u(w)); }
NBT_API void glVertexAttrib1f(GLuint i, GLfloat x) { vattr(i, x, 0.0f, 0.0f, 1.0f); }
NBT_API void glVertexAttrib2f(GLuint i, GLfloat x, GLfloat y) { vattr(i, x, y, 0.0f, 1.0f); }
NBT_API void glVertexAttrib3f(GLuint i, GLfloat x, GLfloat y, GLfloat z) { vattr(i, x, y, z, 1.0f); }
NBT_API void glVertexAttrib4f(GLuint i, GLfloat x, GLfloat y, GLfloat z, GLfloat w) { vattr(i, x, y, z, w); }
NBT_API void glVertexAttrib1fv(GLuint i, const GLfloat *v) { vattr(i, v[0], 0.0f, 0.0f, 1.0f); }
NBT_API void glVertexAttrib2fv(GLuint i, const GLfloat *v) { vattr(i, v[0], v[1], 0.0f, 1.0f); }
NBT_API void glVertexAttrib3fv(GLuint i, const GLfloat *v) { vattr(i, v[0], v[1], v[2], 1.0f); }
NBT_API void glVertexAttrib4fv(GLuint i, const GLfloat *v) { vattr(i, v[0], v[1], v[2], v[3]); }

/* ======================================================================== textures */
static uint32_t pixel_bytes(GLenum fmt, GLenum type, GLsizei w, GLsizei h)
{
    uint32_t ch = 4;
    if (fmt == 0x1907) ch = 3;
    else if (fmt == 0x1909 || fmt == 0x1906) ch = 1;
    else if (fmt == 0x190A) ch = 2;
    uint32_t bpp = (type == 0x8363 || type == 0x8033 || type == 0x8034) ? 2u : ch;
    uint64_t s = (uint64_t)(w > 0 ? (uint32_t)w : 0u) * (uint64_t)(h > 0 ? (uint32_t)h : 0u) * bpp;
    if (s > NBT_MAX_PAYLOAD - 36) abort();
    return (uint32_t)s;
}

NBT_API void glTexImage2D(GLenum target, GLint level, GLint ifmt, GLsizei w, GLsizei h, GLint border,
                          GLenum fmt, GLenum type, const void *data)
{
    uint32_t s = data ? pixel_bytes(fmt, type, w, h) : 0u;
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 52, 36u + s);
    nbt_rec_u32(t, target); nbt_rec_i32(t, level); nbt_rec_i32(t, ifmt);
    nbt_rec_i32(t, w); nbt_rec_i32(t, h); nbt_rec_i32(t, border);
    nbt_rec_u32(t, fmt); nbt_rec_u32(t, type); nbt_rec_u32(t, s);
    if (s) nbt_rec_bytes(t, data, s);
    nbt_rec_send(t);
}

NBT_API void glTexSubImage2D(GLenum target, GLint level, GLint x, GLint y, GLsizei w, GLsizei h,
                             GLenum fmt, GLenum type, const void *data)
{
    uint32_t s = data ? pixel_bytes(fmt, type, w, h) : 0u;
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 56, 36u + s);
    nbt_rec_u32(t, target); nbt_rec_i32(t, level); nbt_rec_i32(t, x);
    nbt_rec_i32(t, y); nbt_rec_i32(t, w); nbt_rec_i32(t, h);
    nbt_rec_u32(t, fmt); nbt_rec_u32(t, type); nbt_rec_u32(t, s);
    if (s) nbt_rec_bytes(t, data, s);
    nbt_rec_send(t);
}

NBT_API void glCompressedTexImage2D(GLenum target, GLint level, GLenum fmt, GLsizei w, GLsizei h,
                                    GLint border, GLsizei size, const void *data)
{
    if (size < 0 || (uint32_t)size > NBT_MAX_PAYLOAD - 28) abort();
    uint32_t body = data ? (uint32_t)size : 0u;
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 139, 28u + body);
    nbt_rec_u32(t, target); nbt_rec_i32(t, level); nbt_rec_u32(t, fmt);
    nbt_rec_i32(t, w); nbt_rec_i32(t, h); nbt_rec_i32(t, border); nbt_rec_i32(t, size);
    if (body) nbt_rec_bytes(t, data, body);
    nbt_rec_send(t);
}

NBT_API void glShaderBinary(GLsizei count, const GLuint *shaders, GLenum format, const void *binary, GLsizei length)
{
    if (count < 0 || length < 0) return;
    if ((count > 0 && !shaders) || (length > 0 && !binary)) return;
    uint64_t total = 12u + (uint64_t)(uint32_t)count * 4u + (uint32_t)length;
    if (total > NBT_MAX_PAYLOAD) abort();
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 110, (uint32_t)total);
    nbt_rec_i32(t, count);
    nbt_rec_u32(t, format);
    nbt_rec_i32(t, length);
    nbt_rec_bytes(t, shaders, 4u * (uint32_t)count);
    nbt_rec_bytes(t, binary, (uint32_t)length);
    nbt_rec_send(t);
}

/* ======================================================================== client-side vertex arrays */
NBT_API void glVertexAttribPointer(GLuint i, GLint size, GLenum type, GLboolean norm, GLsizei stride, const void *ptr)
{
    if (i >= NBT_MAX_ATTR || size < 1 || size > 4 || stride < 0) abort();
    nbt_thread *t = nbt_self();
    nbt_attr *a = &t->attr[i];
    a->size = (uint32_t)size;
    a->type = type;
    a->norm = norm ? 1u : 0u;
    a->stride = (uint32_t)stride;
    a->ptr = ptr;
    a->buffer = t->array_buf;
    if (a->buffer == 0) return;            /* client memory: uploaded at draw time */
    nbt_send_simple(19, 6, i, (uint32_t)size, type, a->norm, (uint32_t)stride, (uint32_t)(uintptr_t)ptr);
}

NBT_API void glEnableVertexAttribArray(GLuint i)
{
    nbt_thread *t = nbt_self();
    if (i < NBT_MAX_ATTR) t->attr[i].enabled = 1;
    nbt_send_simple(20, 1, i);
}

NBT_API void glDisableVertexAttribArray(GLuint i)
{
    nbt_thread *t = nbt_self();
    if (i < NBT_MAX_ATTR) t->attr[i].enabled = 0;
    nbt_send_simple(21, 1, i);
}

static uint32_t scalar_bytes(uint32_t type)
{
    switch (type) {
    case 0x1400: case 0x1401: return 1;
    case 0x1402: case 0x1403: return 2;
    case 0x1404: case 0x1405: case 0x1406: case 0x140C: return 4;
    default: abort();
    }
}

static int any_client_attr(nbt_thread *t)
{
    for (int i = 0; i < NBT_MAX_ATTR; i++)
        if (t->attr[i].enabled && t->attr[i].buffer == 0) return 1;
    return 0;
}

static void upload_client_attrs(nbt_thread *t, uint32_t vertices)
{
    if (vertices == 0) return;
    for (uint32_t i = 0; i < NBT_MAX_ATTR; i++) {
        nbt_attr *a = &t->attr[i];
        if (!a->enabled || a->buffer != 0) continue;
        uint32_t element = a->size * scalar_bytes(a->type);
        uint32_t step = a->stride ? a->stride : element;
        uint64_t bytes = (uint64_t)(vertices - 1) * step + element;
        if (!a->ptr || bytes > NBT_MAX_PAYLOAD - 24) abort();
        nbt_rec_begin(t, 128, 24u + (uint32_t)bytes);
        nbt_rec_u32(t, i);
        nbt_rec_u32(t, a->size);
        nbt_rec_u32(t, a->type);
        nbt_rec_u32(t, a->norm);
        nbt_rec_u32(t, a->stride);
        nbt_rec_u32(t, (uint32_t)bytes);
        nbt_rec_bytes(t, a->ptr, (uint32_t)bytes);
        nbt_rec_send(t);
    }
}

NBT_API void glDrawArrays(GLenum mode, GLint first, GLsizei count)
{
    if (first < 0 || count < 0 || (int64_t)first + count > 0x7FFFFFFF) abort();
    nbt_thread *t = nbt_self();
    if (count > 0) upload_client_attrs(t, (uint32_t)(first + count));
    nbt_send_simple(31, 3, mode, (uint32_t)first, (uint32_t)count);
}

NBT_API void glDrawElements(GLenum mode, GLsizei count, GLenum type, const void *indices)
{
    uint32_t w;
    if (type == 0x1401) w = 1;
    else if (type == 0x1403) w = 2;
    else if (type == 0x1405) w = 4;
    else abort();
    if (count < 0) abort();
    if (count == 0) return;
    nbt_thread *t = nbt_self();
    if (t->element_buf == 0) {
        uint64_t bytes = (uint64_t)(uint32_t)count * w;
        if (!indices || bytes > MiB16 - 16) abort();
        if (any_client_attr(t)) {
            uint32_t mx = 0;
            const uint8_t *p = (const uint8_t *)indices;
            for (GLsizei k = 0; k < count; k++) {
                uint32_t v;
                if (w == 1) v = p[k];
                else if (w == 2) { uint16_t s; memcpy(&s, p + 2 * k, 2); v = s; }
                else memcpy(&v, p + 4 * k, 4);
                if (v > mx) mx = v;
            }
            if (mx == 0xFFFFFFFFu) abort();
            upload_client_attrs(t, mx + 1);
        }
        nbt_rec_begin(t, 129, 16u + (uint32_t)bytes);
        nbt_rec_u32(t, mode);
        nbt_rec_i32(t, count);
        nbt_rec_u32(t, type);
        nbt_rec_u32(t, (uint32_t)bytes);
        nbt_rec_bytes(t, indices, (uint32_t)bytes);
        nbt_rec_send(t);
        return;
    }
    if (any_client_attr(t)) {
        uint32_t mx = 0xFFFFFFFFu;
        nbt_rec_begin(t, 138, 12);
        nbt_rec_i32(t, count);
        nbt_rec_u32(t, type);
        nbt_rec_u32(t, (uint32_t)(uintptr_t)indices);
        if (!nbt_rec_call(t, &mx, 4, (void *)0, 0) || mx == 0xFFFFFFFFu) abort();
        upload_client_attrs(t, mx + 1);
    }
    nbt_send_simple(32, 4, mode, (uint32_t)count, type, (uint32_t)(uintptr_t)indices);
}

/* ======================================================================== synchronous queries */
static GLint location_query(uint32_t op, GLuint p, const GLchar *name)
{
    uint32_t n = name ? (uint32_t)strlen(name) : 0u;
    if (n > NBT_MAX_PAYLOAD - 8) abort();
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, op, 8u + n);
    nbt_rec_u32(t, p);
    nbt_rec_u32(t, n);
    nbt_rec_bytes(t, name, n);
    GLint r = -1;
    if (!nbt_rec_call(t, &r, 4, (void *)0, 0)) return -1;
    return r;
}

NBT_API GLint glGetAttribLocation(GLuint p, const GLchar *name) { return location_query(100, p, name); }
NBT_API GLint glGetUniformLocation(GLuint p, const GLchar *name) { return location_query(101, p, name); }

static int query2(uint32_t op, uint32_t a, uint32_t b, int nfields, void *reply, uint32_t n)
{
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, op, 4u * (uint32_t)nfields);
    if (nfields > 0) nbt_rec_u32(t, a);
    if (nfields > 1) nbt_rec_u32(t, b);
    return nbt_rec_call(t, reply, n, (void *)0, 0);
}

NBT_API void glGetShaderiv(GLuint s, GLenum pname, GLint *out)
{
    GLint v = 0;
    if (query2(102, s, pname, 2, &v, 4) && out) *out = v;
}

NBT_API void glGetProgramiv(GLuint p, GLenum pname, GLint *out)
{
    GLint v = 0;
    if (query2(103, p, pname, 2, &v, 4) && out) *out = v;
}

NBT_API void glGetIntegerv(GLenum pname, GLint *out)
{
    GLint v[16];
    if (!query2(104, pname, 0, 1, v, 64) || !out) return;
    uint32_t n = 1;
    if (pname == 0x0BA2 || pname == 0x0C10 || pname == 0x0C23) n = 4;
    else if (pname == 0x0D3A) n = 2;
    memcpy(out, v, 4 * n);
}

NBT_API GLenum glGetError(void)
{
    GLenum e = 0;
    if (!query2(105, 0, 0, 0, &e, 4)) return 0;
    return e;
}

NBT_API void glGetBooleanv(GLenum pname, GLboolean *out)
{
    uint8_t v[16];
    if (!query2(106, pname, 0, 1, v, 16) || !out) return;
    memcpy(out, v, pname == 0x0C23 ? 4 : 1);
}

NBT_API void glGetFloatv(GLenum pname, GLfloat *out)
{
    GLfloat v[16];
    if (!query2(107, pname, 0, 1, v, 64) || !out) return;
    uint32_t n = 1;
    if (pname == 0x0C22 || pname == 0x8005) n = 4;
    else if (pname == 0x0B70 || pname == 0x846D || pname == 0x846E) n = 2;
    memcpy(out, v, 4 * n);
}

NBT_API void glGetShaderPrecisionFormat(GLenum st, GLenum pt, GLint *range, GLint *precision)
{
    GLint v[3];
    if (!query2(108, st, pt, 2, v, 12)) return;
    if (range) { range[0] = v[0]; range[1] = v[1]; }
    if (precision) *precision = v[2];
}

NBT_API GLenum glCheckFramebufferStatus(GLenum target)
{
    GLenum r = 0;
    if (!query2(109, target, 0, 1, &r, 4)) return 0;
    return r;
}

NBT_API GLboolean glIsEnabled(GLenum cap)
{
    uint32_t r = 0;
    if (!query2(142, cap, 0, 1, &r, 4)) return 0;
    return r != 0;
}

NBT_API void glReadPixels(GLint x, GLint y, GLsizei w, GLsizei h, GLenum fmt, GLenum type, void *pixels)
{
    if (w <= 0 || w > 2048 || h <= 0 || h > 2048 || fmt != 0x1908 || type != 0x1401 || !pixels) return;
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, 120, 24);
    nbt_rec_i32(t, x); nbt_rec_i32(t, y); nbt_rec_i32(t, w); nbt_rec_i32(t, h);
    nbt_rec_u32(t, fmt); nbt_rec_u32(t, type);
    (void)nbt_rec_call(t, pixels, (uint32_t)w * (uint32_t)h * 4u, (void *)0, 0);
}

static void active_query(uint32_t op, GLuint p, GLuint i, GLsizei bufSize, GLsizei *len, GLint *size, GLenum *type, GLchar *name)
{
    if (bufSize < 0) return;
    uint32_t c = (uint32_t)bufSize < 4096u ? (uint32_t)bufSize : 4096u;
    uint8_t namebuf[4096];
    uint32_t hdr[3];
    nbt_thread *t = nbt_self();
    nbt_rec_begin(t, op, 12);
    nbt_rec_u32(t, p); nbt_rec_u32(t, i); nbt_rec_u32(t, c);
    if (!nbt_rec_call(t, hdr, 12, namebuf, c)) return;
    if (name) memcpy(name, namebuf, c);
    if (len) *len = (GLsizei)hdr[0];
    if (size) *size = (GLint)hdr[1];
    if (type) *type = hdr[2];
}

NBT_API void glGetActiveAttrib(GLuint p, GLuint i, GLsizei b, GLsizei *l, GLint *s, GLenum *t, GLchar *n) { active_query(123, p, i, b, l, s, t, n); }
NBT_API void glGetActiveUniform(GLuint p, GLuint i, GLsizei b, GLsizei *l, GLint *s, GLenum *t, GLchar *n) { active_query(124, p, i, b, l, s, t, n); }

NBT_API void glGetVertexAttribiv(GLuint i, GLenum pname, GLint *out)
{
    if (i < NBT_MAX_ATTR && out) {
        nbt_attr *a = &nbt_self()->attr[i];
        switch (pname) {
        case 0x8622: *out = (GLint)a->enabled; return;
        case 0x8623: *out = a->size ? (GLint)a->size : 4; return;
        case 0x8624: *out = (GLint)a->stride; return;
        case 0x8625: *out = a->type ? (GLint)a->type : 0x1406; return;
        case 0x886A: *out = a->norm ? 1 : 0; return;
        case 0x889F: *out = (GLint)a->buffer; return;
        default: break;
        }
    }
    GLint v[4];
    if (!query2(141, i, pname, 2, v, 16) || !out) return;
    memcpy(out, v, pname == 0x8626 ? 16 : 4);
}

/* ======================================================================== local answers / no-ops */
NBT_API const GLubyte *glGetString(GLenum name)
{
    switch (name) {
    case 0x1F00: return (const GLubyte *)"glshim-fwd";
    case 0x1F01: return (const GLubyte *)"glshim-fwd-renderer";
    case 0x1F02: return (const GLubyte *)"OpenGL ES 2.0 (glshim-fwd)";
    case 0x8B8C: return (const GLubyte *)"OpenGL ES GLSL ES 1.00";
    default: return (const GLubyte *)"";
    }
}

static void empty_log(GLsizei bufSize, GLsizei *length, GLchar *log)
{
    if (length) *length = 0;
    if (log && bufSize > 0) log[0] = 0;
}

NBT_API void glGetShaderInfoLog(GLuint s, GLsizei b, GLsizei *l, GLchar *log) { (void)s; empty_log(b, l, log); }
NBT_API void glGetProgramInfoLog(GLuint p, GLsizei b, GLsizei *l, GLchar *log) { (void)p; empty_log(b, l, log); }
NBT_API void glDeleteShader(GLuint s) { (void)s; }
NBT_API void glDeleteProgram(GLuint p) { (void)p; }
NBT_API void glDetachShader(GLuint p, GLuint s) { (void)p; (void)s; }
NBT_API void glClearDepth(GLclampd d) { (void)d; }

NBT_API void glEGLImageTargetTexture2DOES(GLenum target, void *image)
{
    (void)target; (void)image;
    nbt_fd2("NBT EGL image import not implemented\n");
    abort();
}
