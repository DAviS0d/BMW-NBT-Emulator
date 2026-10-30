# Licenses and third-party components

© 2026 davisod & JEtsKi

## This project's code

The code written for this project is licensed under **PolyForm Strict 1.0.0** (see `LICENSE`).
It covers the viewer, the runner, the native controller input, the startup screen, the `.pdds`
decoder and the GLES bridge in `work/bridge-v2/` (the QNX shim `libnbtgl.so` and the renderer
`nbt-glhost-v2.exe`). The license covers only this code. It does not cover the BMW firmware or
the third-party components listed below.

The GLES bridge is a clean-room reimplementation written from a behavioural specification
(`docs/SPEC_GLES_BRIDGE.md`, `docs/RAPORT_CLEANROOM.md`). It contains no code from qemu-mhi2.

## Bundled third-party components

| Component | Location | License | Source |
|---|---|---|---|
| QEMU 11.1.0 for Windows (Stefan Weil build `qemu-w64-setup-20260811`): only `qemu-system-x86_64.exe`, the DLLs it needs and the required BIOS files, unmodified | `work/emulation-tools/qemu-portable/` | GPL-2.0 (`COPYING`), LGPL-2.1 (`COPYING.LIB`) | QEMU 11.1.0 source: <https://download.qemu.org/qemu-11.1.0.tar.xz>; Windows build and its sources: <https://qemu.weilnetz.de/w64/> |
| ANGLE (`mmozeiko/build-angle`, release 2026-10-25), unmodified DLLs | `work/graphics-port/host/angle/angle-x64/bin/` | BSD-3-Clause (`work/graphics-port/host/ANGLE-LICENSE.txt`) | <https://github.com/mmozeiko/build-angle>, <https://chromium.googlesource.com/angle/angle> |
| `d3dcompiler_47.dll` (Microsoft), shipped with the ANGLE build above | `work/graphics-port/host/angle/angle-x64/bin/` | Windows SDK redistributable | Microsoft |

The QEMU binaries are redistributed unmodified and non-commercially. Under GPL-2.0 §3(c), the
complete corresponding source code is available at the addresses above.

## Vehicle coding

`coding/CAFD_00000DED_003_012_025.ncd` is an NBT coding (CAFD 00000DED 3.12.25) with a generic
VIN. It is included with the owner's consent. The emulator uses it to choose the startup
screen.

## Trademarks

BMW, NBT, iDrive and ConnectedDrive are trademarks of BMW AG. Harman, NVIDIA and QNX are
trademarks of their respective owners. This project is not affiliated with any of these
companies.
