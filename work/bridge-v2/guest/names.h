/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): X-macro name lists (GL entry points, Annex A stubs, resolvable EGL procs).
 */
#ifndef NBT_NAMES_H
#define NBT_NAMES_H

/* 121 real GL entry points (sections 2.6 and 2.8, incl. glEGLImageTargetTexture2DOES). */
#define NBT_GL_NAMES(X) \
    X(glViewport) X(glClearColor) X(glClear) X(glFinish) X(glFlush) X(glCreateShader) X(glShaderSource) \
    X(glCompileShader) X(glCreateProgram) X(glAttachShader) X(glLinkProgram) X(glUseProgram) \
    X(glBindAttribLocation) X(glGenBuffers) X(glBindBuffer) X(glBufferData) X(glBufferSubData) \
    X(glVertexAttribPointer) X(glEnableVertexAttribArray) X(glDisableVertexAttribArray) \
    X(glUniform1fv) X(glUniform2fv) X(glUniform3fv) X(glUniform4fv) X(glUniform2f) X(glUniform3f) X(glUniform4f) \
    X(glUniformMatrix2fv) X(glUniformMatrix3fv) X(glUniformMatrix4fv) X(glUniform1f) X(glUniform1i) \
    X(glDrawArrays) X(glDrawElements) X(glEnable) X(glDisable) X(glBlendFunc) X(glDepthFunc) X(glCullFace) \
    X(glFrontFace) X(glDepthMask) X(glClearDepthf) X(glLineWidth) X(glPolygonOffset) X(glGenTextures) \
    X(glBindTexture) X(glTexImage2D) X(glTexParameteri) X(glActiveTexture) X(glPixelStorei) X(glTexSubImage2D) \
    X(glGenerateMipmap) X(glTexParameterf) X(glBindFramebuffer) X(glBindRenderbuffer) X(glFramebufferTexture2D) \
    X(glRenderbufferStorage) X(glFramebufferRenderbuffer) X(glScissor) X(glColorMask) X(glClearStencil) \
    X(glStencilMask) X(glStencilFunc) X(glStencilOp) X(glBlendFuncSeparate) X(glBlendEquation) \
    X(glBlendEquationSeparate) X(glStencilMaskSeparate) X(glStencilFuncSeparate) X(glStencilOpSeparate) \
    X(glGenFramebuffers) X(glGenRenderbuffers) X(glUniform1iv) X(glUniform2iv) X(glUniform3iv) X(glUniform4iv) \
    X(glUniform2i) X(glUniform3i) X(glUniform4i) X(glVertexAttrib1f) X(glVertexAttrib2f) X(glVertexAttrib3f) \
    X(glVertexAttrib4f) X(glVertexAttrib1fv) X(glVertexAttrib2fv) X(glVertexAttrib3fv) X(glVertexAttrib4fv) \
    X(glDepthRangef) X(glBlendColor) X(glHint) X(glGetAttribLocation) X(glGetUniformLocation) X(glGetShaderiv) \
    X(glGetProgramiv) X(glGetIntegerv) X(glGetError) X(glGetBooleanv) X(glGetFloatv) X(glGetShaderPrecisionFormat) \
    X(glCheckFramebufferStatus) X(glShaderBinary) X(glReadPixels) X(glGetActiveAttrib) X(glGetActiveUniform) \
    X(glDeleteTextures) X(glDeleteBuffers) X(glDeleteFramebuffers) X(glDeleteRenderbuffers) \
    X(glCompressedTexImage2D) X(glCopyTexSubImage2D) X(glGetVertexAttribiv) X(glIsEnabled) X(glSampleCoverage) \
    X(glGetString) X(glGetShaderInfoLog) X(glGetProgramInfoLog) X(glDeleteShader) X(glDeleteProgram) \
    X(glDetachShader) X(glClearDepth) X(glEGLImageTargetTexture2DOES)

/* Annex A: 82 unsupported functions. */
#define NBT_STUB_NAMES(X) \
    X(glBeginPerfMonitorAMD) X(glBindVertexArrayOES) X(glCompressedTexImage3DOES) X(glCompressedTexSubImage2D) \
    X(glCompressedTexSubImage3DOES) X(glCopyTexImage2D) X(glCopyTexSubImage3DOES) X(glDeleteFencesNV) \
    X(glDeletePerfMonitorsAMD) X(glDeleteVertexArraysOES) X(glDisableDriverControlQCOM) X(glDiscardFramebufferEXT) \
    X(glEGLImageTargetRenderbufferStorageOES) X(glEnableDriverControlQCOM) X(glEndPerfMonitorAMD) \
    X(glEndTilingQCOM) X(glExtGetBufferPointervQCOM) X(glExtGetBuffersQCOM) X(glExtGetFramebuffersQCOM) \
    X(glExtGetProgramBinarySourceQCOM) X(glExtGetProgramsQCOM) X(glExtGetRenderbuffersQCOM) \
    X(glExtGetShadersQCOM) X(glExtGetTexLevelParameterivQCOM) X(glExtGetTexSubImageQCOM) \
    X(glExtGetTexturesQCOM) X(glExtIsProgramBinaryQCOM) X(glExtTexObjectStateOverrideiQCOM) X(glFinishFenceNV) \
    X(glFramebufferTexture3DOES) X(glGenFencesNV) X(glGenPerfMonitorsAMD) X(glGenVertexArraysOES) \
    X(glGetAttachedShaders) X(glGetBufferParameteriv) X(glGetBufferPointervOES) X(glGetDriverControlStringQCOM) \
    X(glGetDriverControlsQCOM) X(glGetFenceivNV) X(glGetFramebufferAttachmentParameteriv) \
    X(glGetPerfMonitorCounterDataAMD) X(glGetPerfMonitorCounterInfoAMD) X(glGetPerfMonitorCounterStringAMD) \
    X(glGetPerfMonitorCountersAMD) X(glGetPerfMonitorGroupStringAMD) X(glGetPerfMonitorGroupsAMD) \
    X(glGetProgramBinaryOES) X(glGetRenderbufferParameteriv) X(glGetShaderSource) X(glGetTexParameterfv) \
    X(glGetTexParameteriv) X(glGetTexStreamDeviceAttributeivIMG) X(glGetTexStreamDeviceNameIMG) \
    X(glGetUniformfv) X(glGetUniformiv) X(glGetVertexAttribPointerv) X(glGetVertexAttribfv) X(glIsBuffer) \
    X(glIsFenceNV) X(glIsFramebuffer) X(glIsProgram) X(glIsRenderbuffer) X(glIsShader) X(glIsTexture) \
    X(glIsVertexArrayOES) X(glMapBufferOES) X(glMultiDrawArraysEXT) X(glMultiDrawElementsEXT) \
    X(glProgramBinaryOES) X(glReleaseShaderCompiler) X(glSelectPerfMonitorCountersAMD) X(glSetFenceNV) \
    X(glStartTilingQCOM) X(glTestFenceNV) X(glTexBindStreamIMG) X(glTexImage3DOES) X(glTexParameterfv) \
    X(glTexParameteriv) X(glTexSubImage3DOES) X(glUnmapBufferOES) X(glValidateProgram) \
    X(glVertexAttribPointerBounds)

/* 29 EGL functions that eglGetProcAddress resolves (section 2.9). */
#define NBT_EGL_PROC_NAMES(X) \
    X(eglGetSystemTimeFrequencyNV) X(eglGetSystemTimeNV) X(eglCreateImageKHR) X(eglDestroyImageKHR) \
    X(eglBindAPI) X(eglChooseConfig) X(eglCreateContext) X(eglCreatePbufferSurface) X(eglCreateWindowSurface) \
    X(eglDestroyContext) X(eglDestroySurface) X(eglGetConfigAttrib) X(eglGetConfigs) X(eglGetCurrentContext) \
    X(eglGetCurrentDisplay) X(eglGetCurrentSurface) X(eglGetDisplay) X(eglGetError) X(eglGetPlatformDisplay) \
    X(eglInitialize) X(eglMakeCurrent) X(eglQueryString) X(eglQuerySurface) X(eglReleaseThread) \
    X(eglSwapBuffers) X(eglSwapInterval) X(eglTerminate) X(eglWaitGL) X(eglWaitNative)

#endif
