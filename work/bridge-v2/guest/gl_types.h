/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): minimal Khronos EGL/GLES 2.0 C types for the i386 ABI.
 */
#ifndef NBT_GL_TYPES_H
#define NBT_GL_TYPES_H
#include <stdint.h>

typedef unsigned int GLenum;
typedef unsigned char GLboolean;
typedef unsigned int GLbitfield;
typedef int GLint;
typedef int GLsizei;
typedef unsigned int GLuint;
typedef float GLfloat;
typedef float GLclampf;
typedef double GLclampd;
typedef char GLchar;
typedef unsigned char GLubyte;
typedef void GLvoid;
typedef long GLsizeiptr;
typedef long GLintptr;

typedef void *EGLDisplay;
typedef void *EGLConfig;
typedef void *EGLSurface;
typedef void *EGLContext;
typedef void *EGLClientBuffer;
typedef void *EGLImageKHR;
typedef void *EGLNativeDisplayType;
typedef void *EGLNativeWindowType;
typedef void *EGLNativePixmapType;
typedef int32_t EGLint;
typedef unsigned int EGLBoolean;
typedef unsigned int EGLenum;
typedef intptr_t EGLAttrib;
typedef uint64_t EGLuint64NV;

#endif
