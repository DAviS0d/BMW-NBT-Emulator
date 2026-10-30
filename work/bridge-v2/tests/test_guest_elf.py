"""© 2026 davisod & JEtsKi
Guest ABI self-test: parses guest/libnbtgl.so (ELF32 i386) and checks the section 2.1 contract.

Checks: ELF32/EM_386/ET_DYN, SONAME, no DT_NEEDED, no DT_GNU_HASH, DT_HASH present, DT_FINI == _fini,
no PT_GNU_RELRO, no TEXTREL, exactly the 249 expected exports (independent list below, typed from the spec),
undefined symbols only from the allowed import list.
"""
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "guest", "libnbtgl.so")

ALLOWED_IMPORTS = set("""atoi usleep mem_offset64 abort pthread_getspecific pthread_setspecific pthread_key_create
pthread_self pthread_create pthread_join send getpid read write close fflush socket connect setsockopt select
strcmp strlen __get_errno_ptr malloc realloc free printf vsnprintf mmap64 ClockTime getenv ThreadCtl""".split())

EGL = """eglGetDisplay eglGetPlatformDisplay eglInitialize eglGetConfigs eglChooseConfig eglGetConfigAttrib
eglCreateWindowSurface eglCreatePbufferSurface eglCreateContext eglMakeCurrent eglQuerySurface eglSwapBuffers
eglSwapInterval eglGetError eglTerminate eglReleaseThread eglWaitGL eglWaitNative eglDestroySurface
eglDestroyContext eglBindAPI eglQueryAPI eglQueryContext eglSurfaceAttrib eglWaitClient eglBindTexImage
eglReleaseTexImage eglCopyBuffers eglCreatePixmapSurface eglCreatePbufferFromClientBuffer eglQueryString
eglGetSystemTimeFrequencyNV eglGetSystemTimeNV eglGetCurrentDisplay eglGetCurrentContext eglGetCurrentSurface
eglCreateImageKHR eglDestroyImageKHR eglGetProcAddress NvEglRegClientApi""".split()

LOGGING = "vslogf slogf slog2f slog2c slog2_register".split()

GL = """glViewport glClearColor glClear glFinish glFlush glCreateShader glShaderSource glCompileShader glCreateProgram
glAttachShader glLinkProgram glUseProgram glBindAttribLocation glGenBuffers glBindBuffer glBufferData glBufferSubData
glVertexAttribPointer glEnableVertexAttribArray glDisableVertexAttribArray glUniform1fv glUniform2fv glUniform3fv
glUniform4fv glUniform2f glUniform3f glUniform4f glUniformMatrix2fv glUniformMatrix3fv glUniformMatrix4fv glUniform1f
glUniform1i glDrawArrays glDrawElements glEnable glDisable glBlendFunc glDepthFunc glCullFace glFrontFace glDepthMask
glClearDepthf glLineWidth glPolygonOffset glGenTextures glBindTexture glTexImage2D glTexParameteri glActiveTexture
glPixelStorei glTexSubImage2D glGenerateMipmap glTexParameterf glBindFramebuffer glBindRenderbuffer
glFramebufferTexture2D glRenderbufferStorage glFramebufferRenderbuffer glScissor glColorMask glClearStencil
glStencilMask glStencilFunc glStencilOp glBlendFuncSeparate glBlendEquation glBlendEquationSeparate
glStencilMaskSeparate glStencilFuncSeparate glStencilOpSeparate glGenFramebuffers glGenRenderbuffers glUniform1iv
glUniform2iv glUniform3iv glUniform4iv glUniform2i glUniform3i glUniform4i glVertexAttrib1f glVertexAttrib2f
glVertexAttrib3f glVertexAttrib4f glVertexAttrib1fv glVertexAttrib2fv glVertexAttrib3fv glVertexAttrib4fv
glDepthRangef glBlendColor glHint glGetAttribLocation glGetUniformLocation glGetShaderiv glGetProgramiv
glGetIntegerv glGetError glGetBooleanv glGetFloatv glGetShaderPrecisionFormat glCheckFramebufferStatus
glShaderBinary glReadPixels glGetActiveAttrib glGetActiveUniform glDeleteTextures glDeleteBuffers
glDeleteFramebuffers glDeleteRenderbuffers glCompressedTexImage2D glCopyTexSubImage2D glGetVertexAttribiv
glIsEnabled glSampleCoverage glGetString glGetShaderInfoLog glGetProgramInfoLog glDeleteShader glDeleteProgram
glDetachShader glClearDepth glEGLImageTargetTexture2DOES""".split()

STUBS = """glBeginPerfMonitorAMD glBindVertexArrayOES glCompressedTexImage3DOES glCompressedTexSubImage2D
glCompressedTexSubImage3DOES glCopyTexImage2D glCopyTexSubImage3DOES glDeleteFencesNV glDeletePerfMonitorsAMD
glDeleteVertexArraysOES glDisableDriverControlQCOM glDiscardFramebufferEXT glEGLImageTargetRenderbufferStorageOES
glEnableDriverControlQCOM glEndPerfMonitorAMD glEndTilingQCOM glExtGetBufferPointervQCOM glExtGetBuffersQCOM
glExtGetFramebuffersQCOM glExtGetProgramBinarySourceQCOM glExtGetProgramsQCOM glExtGetRenderbuffersQCOM
glExtGetShadersQCOM glExtGetTexLevelParameterivQCOM glExtGetTexSubImageQCOM glExtGetTexturesQCOM
glExtIsProgramBinaryQCOM glExtTexObjectStateOverrideiQCOM glFinishFenceNV glFramebufferTexture3DOES glGenFencesNV
glGenPerfMonitorsAMD glGenVertexArraysOES glGetAttachedShaders glGetBufferParameteriv glGetBufferPointervOES
glGetDriverControlStringQCOM glGetDriverControlsQCOM glGetFenceivNV glGetFramebufferAttachmentParameteriv
glGetPerfMonitorCounterDataAMD glGetPerfMonitorCounterInfoAMD glGetPerfMonitorCounterStringAMD
glGetPerfMonitorCountersAMD glGetPerfMonitorGroupStringAMD glGetPerfMonitorGroupsAMD glGetProgramBinaryOES
glGetRenderbufferParameteriv glGetShaderSource glGetTexParameterfv glGetTexParameteriv
glGetTexStreamDeviceAttributeivIMG glGetTexStreamDeviceNameIMG glGetUniformfv glGetUniformiv
glGetVertexAttribPointerv glGetVertexAttribfv glIsBuffer glIsFenceNV glIsFramebuffer glIsProgram glIsRenderbuffer
glIsShader glIsTexture glIsVertexArrayOES glMapBufferOES glMultiDrawArraysEXT glMultiDrawElementsEXT
glProgramBinaryOES glReleaseShaderCompiler glSelectPerfMonitorCountersAMD glSetFenceNV glStartTilingQCOM
glTestFenceNV glTexBindStreamIMG glTexImage3DOES glTexParameterfv glTexParameteriv glTexSubImage3DOES
glUnmapBufferOES glValidateProgram glVertexAttribPointerBounds""".split()


class Elf:
    def __init__(self, data):
        self.d = data
        if data[:4] != b"\x7fELF":
            raise ValueError("not ELF")
        self.cls, self.endian = data[4], data[5]
        (self.type, self.machine, _, _, self.phoff, self.shoff, _, _, self.phentsize, self.phnum,
         self.shentsize, self.shnum, self.shstrndx) = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)

    def phdrs(self):
        for i in range(self.phnum):
            yield struct.unpack_from("<IIIIIIII", self.d, self.phoff + i * self.phentsize)

    def shdrs(self):
        for i in range(self.shnum):
            yield struct.unpack_from("<IIIIIIIIII", self.d, self.shoff + i * self.shentsize)

    def vaddr_to_off(self, va):
        for (ptype, off, vaddr, _, filesz, _, _, _) in self.phdrs():
            if ptype == 1 and vaddr <= va < vaddr + filesz:
                return off + (va - vaddr)
        raise ValueError(hex(va))

    def cstr(self, off):
        end = self.d.index(b"\0", off)
        return self.d[off:end].decode()


def main():
    data = open(LIB, "rb").read()
    e = Elf(data)
    fails = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            fails.append(msg)

    check(e.cls == 1 and e.endian == 1, "ELF32 little-endian")
    check(e.type == 3, "ET_DYN shared object")
    check(e.machine == 3, "EM_386")

    ptypes = [p[0] for p in e.phdrs()]
    check(0x6474E552 not in ptypes, "no PT_GNU_RELRO (-z norelro)")
    dyn = [p for p in e.phdrs() if p[0] == 2]
    check(len(dyn) == 1, "one PT_DYNAMIC")
    entries = []
    off = dyn[0][1]
    while True:
        tag, val = struct.unpack_from("<iI", data, off)
        off += 8
        if tag == 0:
            break
        entries.append((tag, val))
    tags = {}
    for t, v in entries:
        tags.setdefault(t, []).append(v)
    strtab = e.vaddr_to_off(tags[5][0])
    symtab = e.vaddr_to_off(tags[6][0])
    check(1 not in tags, "no DT_NEEDED")
    check(0x6FFFFEF5 not in tags, "no DT_GNU_HASH")
    check(4 in tags, "DT_HASH present")
    check(22 not in tags and not any(t == 30 and (v & 4) for t, v in entries), "no TEXTREL")
    soname = e.cstr(strtab + tags[14][0]) if 14 in tags else None
    check(soname == "libnbtgl.so", f"DT_SONAME = {soname}")

    nsyms = struct.unpack_from("<II", data, e.vaddr_to_off(tags[4][0]))[1]
    exports, imports = {}, set()
    for i in range(1, nsyms):
        name_off, value, size, info, other, shndx = struct.unpack_from("<IIIBBH", data, symtab + 16 * i)
        name = e.cstr(strtab + name_off)
        bind, vis = info >> 4, other & 3
        if shndx == 0:
            if name:
                imports.add(name)
        elif bind in (1, 2) and vis == 0:
            exports[name] = value
    expected = set(EGL + LOGGING + GL + STUBS + ["_fini"])
    check(len(EGL) == 40 and len(LOGGING) == 5 and len(GL) == 121 and len(STUBS) == 82, "expected list sizes 40/5/121/82")
    check(len(expected) == 249, f"expected export set has 249 names ({len(expected)})")
    check(set(exports) == expected, f"exported set == expected ({len(exports)} exported)")
    if set(exports) != expected:
        print("  extra:", sorted(set(exports) - expected))
        print("  missing:", sorted(expected - set(exports)))
    bad = sorted(imports - ALLOWED_IMPORTS)
    check(not bad, f"imports within allowed set ({len(imports)} used) {bad if bad else ''}")
    print("  imports:", " ".join(sorted(imports)))
    check(13 in tags and tags[13][0] == exports.get("_fini"), "DT_FINI points at exported _fini")

    # Regression: calls into fixed HmiMain3D addresses must be absolute-indirect. A PC-relative
    # "call rel32" is resolved for load base 0 and would jump to firmware_address + library_base.
    firmware = {0x080B45D8, 0x080B007E, 0x08A0A732, 0x080968A0}
    bad_calls = []
    for (ptype, off, vaddr, _, filesz, _, flags, _) in e.phdrs():
        if ptype != 1 or not (flags & 1):
            continue
        for j in range(off, off + filesz - 5):
            if data[j] == 0xE8:
                rel = struct.unpack_from("<i", data, j + 1)[0]
                tgt = (vaddr + (j - off) + 5 + rel) & 0xFFFFFFFF
                if tgt in firmware:
                    bad_calls.append(hex(tgt))
    check(not bad_calls, f"no PC-relative calls to firmware addresses {bad_calls if bad_calls else ''}")

    print("GUEST_ELF_PASS" if not fails else f"GUEST_ELF_FAIL ({len(fails)})")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
