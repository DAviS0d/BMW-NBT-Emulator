<!-- © 2026 davisod & JEtsKi — README of bridge v2 (clean-room GLES/EGL bridge: QNX guest library + Windows renderer). -->

# Bridge v2 — clean-room GLES/EGL forwarding bridge

© 2026 davisod & JEtsKi

A new, independent implementation of the NBT GLES/EGL bridge, written **only** from
`docs/SPEC_GLES_BRIDGE.md` (plus public Khronos/QNX/Win32 API knowledge, the ANGLE headers and
import libraries and the Zig toolchain). No previous project code was read.

| Part | Output | What it is |
| --- | --- | --- |
| `guest/` | `guest/libnbtgl.so` | ELF32 i386 shared library for QNX 6.5 (`LD_PRELOAD` into `HmiMain3D`): EGL 1.4 / GLES 2.0 exports, record serialisation, 64 KiB batching, global lock, userspace legacy virtio-console driver (polling), DMA rings, MTP worker thread and keyboard HAL. |
| `host/` | `host/nbt-glhost-v2.exe` | Windows x86-64 renderer: socket/stdio channel, DMA attach + guarded cross-process ring I/O, ANGLE (EGL pbuffer + GLES 2 contexts per guest process), opcode execution with byte-exact replies, NVIDIA shader replacement by hash, native frame cache, PPM publication on a worker thread. |
| `tests/` | — | Self-tests (no VM): guest ELF/ABI check, DMA ring contract harness, renderer end-to-end with real ANGLE. |

## Build

```
cd work\bridge-v2
py -3 build.py            # guest + host, prints the sha256 of each output
py -3 build.py guest      # only libnbtgl.so
py -3 build.py host       # only nbt-glhost-v2.exe
py -3 build.py tests      # tests\ring_harness.exe (host ring/validator modules without GL)
```

Toolchain: `work/graphics-port/toolchain/zig-x86_64-windows-0.15.2/zig.exe` (`zig cc`).

* Guest: `-target x86-linux-gnu -mcpu=pentium4 -mstackrealign -ffreestanding -fno-builtin
  -fno-stack-protector -nostdlib -fPIC -O2 -shared -fvisibility=hidden
  -Wl,--hash-style=sysv -Wl,-z,norelro -Wl,-soname,libnbtgl.so`. Exports are marked explicitly
  (`NBT_API`); `memcpy/memset/memmove/memcmp` are provided statically with hidden visibility.
* Host: `-target x86_64-windows-gnu -O2`, linked with ANGLE `libEGL.dll.lib`, `libGLESv2.dll.lib`
  and `ws2_32`. At run time `libEGL.dll`/`libGLESv2.dll` from `angle-x64/bin` must be on `PATH`
  (the existing bridge script already does that).

The renderer is a drop-in candidate for `nbt-glhost-dma.exe` / `nbt-glhost-dma-fast.exe`; nothing
in the existing tree was replaced — copying it over is a separate, deliberate step.

## Tests

```
py -3 tests\test_guest_elf.py       # GUEST_ELF_PASS
py -3 build.py tests && tests\ring_harness.exe   # DMA_CONTRACT_PASS ...
py -3 tests\test_host_e2e.py        # HOST_E2E_PASS (needs a D3D-capable GPU/WARP for ANGLE)
```

* `test_guest_elf.py` parses the ELF itself: ELF32/EM_386/ET_DYN, SONAME, no `DT_NEEDED`, no
  `DT_GNU_HASH`, `DT_HASH` present, no RELRO/TEXTREL, `DT_FINI` = exported `_fini`, the exported
  set equals an independently typed list of the 249 names, imports ⊆ the allowed list.
* `ring_harness.exe` maps a 135168-byte region (with guard pages) in its own process and runs the
  real `dmaring.c` through `ReadProcessMemory`/`NtWriteVirtualMemory` against a guest-protocol
  simulator thread: 8 MiB + 73 bytes each direction, cursors starting at `0xFFFFFFF0` (TX) /
  `0xFFFFFFA1` (RX) so the 32-bit cursors wrap, >100 ring wraps, read sizes 1/4/8/4095/65535/
  65536/121, write restrictions (EPERM/EINVAL list of §5.4), invalid occupancy → EPROTO, a blocked
  reader returning 0 on control EOF, untouched guard bytes; also validator rules and FNV-1a vectors.
* `test_host_e2e.py` runs the real renderer with ANGLE in stdio mode and socket mode: getters and
  reply sizes, op 138 on indices `[2, 7, 1]` → 7, hidden `glGetBufferParameteriv` error parity,
  `glReadPixels`, PPM flip/size/atomic replace, invalid record, video record → exit 3, op 144 without
  config → ack 0 without the disconnect line, `control_eof=1 control_joined=1`, line ordering.

Not run here (by design): QEMU, the HMI, the parity capture test of spec §6.1 (its inputs live
outside the clean-room boundary).

## Design notes

Guest (`guest/`):

* `link.c` — per-thread state behind one `pthread_key` (created once with a CAS state machine,
  freed by the key destructor); record = 20-byte prefix `[119,4,pid,op,L]` + payload, built in a
  per-thread growable buffer; one global spin lock (`usleep(1000)` between attempts); one 64 KiB
  batch flushed per the §2.3 rules; synchronous records keep the lock until the whole reply has
  been read. Lazy transport init with a 0→1→2 state machine.
* `virtio.c` — PCI mechanism #1 scan, legacy registers, vring layout of §4.1, one in-flight buffer
  (descriptor 0) per data queue, control queue with min(n,16) 256-byte slots, MULTIPORT handshake,
  per-queue statistics for the `NBT_VFAST_PERF_QUEUE` markers.
* `dma.c` — region header/nonce, cursor publication (value, barrier, complement, barrier), valid
  reads (value, complement, value), send/receive with the stop-word check and 10 s timeout, op 144
  bootstrap over port 1.
* `input.c` / `keyboard.c` — MTP worker (TCP 127.0.0.1:50123), port 2 framer (BE u16 total length,
  4096-byte buffer), keyboard HAL with the identity bytes and read-only sink resolution of §3.3.
  Calls to the fixed `HmiMain3D` addresses go through `fw_addr()` (an empty asm barrier), so the
  compiler emits absolute register-indirect calls. A PC-relative `call rel32` to a constant
  address in a PIC library is resolved for load base 0 and jumps to *address + library base*
  (this was the SIGSEGV of the first HMI run). `test_guest_elf.py` now checks for it. The
  `host_to_native` counter in `NBT_MTP_VIRTIO_*` lines counts bytes received from the host,
  including the current chunk.
* `gles.c`, `egl.c`, `stubs.c` — the 249 exports; `eglGetProcAddress` uses an X-macro table
  (`names.h`) of all `gl*` exports + the 29 resolvable EGL names.

Host (`host/`):

* `channel.c` — stdio or socket transport; stdin lifetime thread; “cancelled” = control EOF or
  closing; switches to the DMA ring after a successful op 144.
* `dmaring.c` — every access goes through `glh_dma_mem_read/write`, which enforce the §5.4 bounds
  and write whitelist *before* touching memory; writes use `NtWriteVirtualMemory` (fallback
  `WriteProcessMemory`), reads `ReadProcessMemory`; TX is read in bulk (everything available up
  to the ring end in one cross-process read, one tail publication per block) into a 64 KiB cache.
* `idle.c` — spin with `YieldProcessor` for 3 ms after the last activity, then 1 ms waits on a
  `CREATE_WAITABLE_TIMER_HIGH_RESOLUTION` timer (fallback `Sleep(1)`).
* `render.c` — window/initial frame, clients (own context + pbuffer + 2²⁰-entry name table +
  blend metadata), opcode table of §5.8 with exactly the hidden GL calls of §5.9.
* `publish.c` — readback stays on the GL thread; the RGBA buffer is swapped with the worker's
  buffer (no copy) after waiting for the previous frame, so exactly one frame can be pending and
  none is skipped; `.tmp` + `MoveFileEx(REPLACE_EXISTING|WRITE_THROUGH)`.

## Spec ambiguities and the choices made

1. **Hex formatting of markers** (`physical=<hex>`, `bar0=<hex>`, `pfn=…`, EGL error codes):
   printed as `0x%x` (lower case, `0x` prefix). The DMA config file is parsed as hex without prefix
   (explicit in the spec); `sscanf %llx` accepts both.
2. **`VIRTIO_DMA_ALLOC n=<k>`**: `k` is a 1-based allocation sequence number.
3. **`VIRTIO_CONTROL_SEND id=…`**: ids printed unsigned (`4294967295` for the DEVICE_READY id).
4. **Notify during queue setup**: buffers posted before DRIVER_OK (queue 4, 6 and the control
   slots) are posted without a notify; step 7 notifies queues 4 and 6 as specified. Reposting a
   control slot after a message notifies queue 2.
5. **Guest DMA wait clock**: the 10 s window is measured from the first 65536-iteration
   checkpoint of the current wait (avoids a `ClockTime` call per chunk); reset on progress.
6. **Queue-6 polling statistics**: completions found by the non-blocking poll count as
   `completed` and `immediate` (no wait iterations).
7. **`glBufferSubData(…, data=NULL)`**: S is still sent (payload 12) exactly as written in §2.6;
   the host would reject such a record. `glTexSubImage2D` with NULL data sends S = 0 like op 52.
8. **Negative counts / NULL arrays** not covered by the spec (`glGenBuffers/glGenTextures` with
   n<0, `glUniform*fv` with count<0 or NULL, `glShaderSource` with NULL strings,
   `glShaderBinary` with NULL arrays) → nothing is sent (no abort).
9. **Keyboard capability UI probing** (display/manager getters) is only done when the sink is
   `queue_ready`; otherwise those fields print as NULL/0.
10. **`_fini` flush** ignores a ring failure (the host may already be gone) instead of aborting
    the exiting process.
11. **Host PID 0 after other clients**: the initial context is not in the client list, so a later
    switch to PID 0 creates a new client (literal reading of §5.6). Production guests never send 0.
12. **Gen ops with name 0**: the created object is stored at index 0 (literal reading); op 130
    still ignores id 0.
13. **Blend override inside op 129**: order is EBO save → bind 0 → blend save/set → draw → blend
    restore → EBO restore (none of these calls can raise GL errors).
14. **Native frame cache**: ids match globally for op 131/132; only op 133 filters by owner.
15. **`MHI2_GL_DUMP_CLIENTS`**: the per-client PPM is written synchronously; the readback is shared
    with the main publication when both happen on the same swap (one `glReadPixels`).
16. **`glhost: OOM <len>`**: printed when the payload buffer cannot be allocated; the session ends
    like a normal break (with the disconnect line).
17. **Fatal exits 1/3/4/5** exit immediately but still write the DMA stop word if attached.
18. **A second op 144** (DMA already attached) is answered with ack 0 on the socket and ends the
    session silently.
19. **Op 120/131 pixel buffer** is zero-initialised before `glReadPixels`.
20. **stdio mode** answers op 144 on stdout (the “base” stream).
21. **Spec section 2.7 does not exist** in the document; the 249-symbol set is exactly
    §2.5 (40) + §2.6/§2.8 (121 incl. `glEGLImageTargetTexture2DOES`) + §2.11 (5) + Annex A (82) +
    `_fini`.
