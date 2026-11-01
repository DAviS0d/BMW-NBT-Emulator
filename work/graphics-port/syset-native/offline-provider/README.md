# Native offline coding provider

`libnbt_offline_syset.so` is a VM-only input provider for the exact recovered `HmiMain3D.uncompressed.elf`. It supplies the owner's decoded NCD coding bytes to the original HMI configuration event, parser, model and listener path. It does not implement a SystemSettings broker server.

Build: `python work/graphics-port/syset-native/offline-provider/build.py` from the repository root. Zig 0.15.2 targets ELF32 i386, SysV hash, realigned stack, freestanding/no standard runtime linkage, no RELRO. The generated `.so` has `DT_INIT` pointing to `_init`, with nine unresolved imports that are already native runtime APIs: HBSyslog::vlogMsg, CHBBuffer ctor/copy/size/dtor, printf, fflush, pthread_create, usleep.

Input provenance is `work/graphics-port/coding-input/input-validation.json`, original source `C:/Data/CAF/CAFD_00000DED_003_012_025.ncd`, source SHA-256 `9a981b7f48456385bdeb06538bf46587dcc2f3a3a940426fe2b9d65ed434b3f3`. All eight decoded `segment_300000.bin` through `segment_300700.bin` payloads are embedded byte-for-byte. The CAF_ID payload contains its original version 3.12.25; the DSI envelope preserves that actual version for every CB.

The original HMI native metadata expects application HMI version 1.1 and eight CB slots 0x3000..0x3007 followed by five telephone-buffer keys 0xf0004001..0xf0004005. App DSI parser `0x093e30a2` reads a 6-byte header: u16LE major, u16LE minor, u16LE child-data length. It iterates metadata insertion order. Each CB record is state byte; state 1 adds three version bytes, u16LE raw length, and payload. State 0 consumes just one byte and preserves that node. Key state 0 similarly consumes one byte and retains current data. There are no child IDs, padding or terminators in this DSI envelope. The 1102-byte generated stream has 1043 unchanged NCD payload bytes, 48 CB header bytes, five key-skip bytes, and six application-header bytes.

The original CB parser `0x093dd726` compares the received CB major version only against native major 3 (branch 0x093dd7fa); app parser compares app major only (0x093e315f). Native HMI metadata CB version is 3.9.1. The provider does not rewrite the supplied version to match it; actual 3.12.25 is major-compatible. Every NCD block length exactly matches its native CB size, so no truncation/extension is requested.

The preload intercepts the exported native variadic HBSyslog::logMsg entry point `_ZN8HBSyslog6logMsgEiNS_8SeverityEPKcz`. HMI helper 0x08f99014 has already fully formatted the CHMISysetClientConfigImpl constructor message before calling this log function at 0x08f9906e. The hook only reads that existing text to capture the actual `this` and `listener` hex pointers. It does not format the message again or consume the caller's argument cursor. Every call is forwarded with unchanged domain, severity, format pointer and original va_list to `_ZN8HBSyslog7vlogMsgEiNS_8SeverityEPKcPc`.

Original libsys_colibry.so.4 logMsg implementation at 0x230e2 is a simple varargs-to-vlogMsg wrapper; it returns preserving vlogMsg's EAX. The hook does the same; `hbsyslog.dis.txt` records that native evidence.

On preload initialization, a worker waits for that captured constructor input and the original object's publication:

1. `client` and `listener` are the actual pointers captured from the native constructor log.
2. `thread = listener-0xc0`, expected vtable `0x0963b220`.
3. `*(void**)(thread+0xc4)` must equal the captured client, expected vtable `0x09760e40`.
4. Native model root `*(void**)0x099a7d14` must be nonzero. Vtable processEvent slot +0x28 must be `0x08f99da0`.

Root's live GDB inspection confirmed this publication route: at 0x089eb790, thread=0x09a15168, client=0x09b240d0, native constructor listener=0x09a15228, root=0x09b24118. The late VariantServer global 0x09907250 is still zero at this point. The obsolete late-global provider is preserved in `history/late-global`; the current provider does not require that global.

The worker rechecks the publication chain, then creates an actual native CHBBuffer using original constructors and copy method. It passes an event view with ID 0x80000000 at +0xc, the client's unchanged current generation tag at +0x10, and that buffer at +0x14 to ORIGINAL `processEvent` at 0x08f99da0. That original method owns its mutex, constructs CHBByteStream, calls original DSIRead 0x093dc0cf, and notifies all real ISysetClientListeners through their original vtable+8 methods. The unused first three event-header words are zeroed and never read by this original method. All model mutation and notifications happen inside original native code.

The original CHMISysetClientConfigImpl object is fully published only after its constructor returns: instruction 0x089eb790 stores it at thread+0xc4. The provider waits for that publication rather than intercepting the constructor or scanning heap memory.

Runtime diagnostics start `NBT_OFFLINE_SYSET`. Exports for inspection/manual integration:

- `nbt_offline_syset_apply(void *client)`: one-time delivery using a validated actual client object; returns -2 for invalid native object chain or 3 after original event returns.
- `nbt_offline_syset_status`: 0 before worker, 1 waiting, 2 delivering, 3 original event returned, -1 native pointer timeout, -3 buffer-size failure, -4 pthread creation error.
- `nbt_offline_syset_captured_client`, `nbt_offline_syset_captured_listener`: pointers from the original constructor text.
- `nbt_offline_syset_thread`, `nbt_offline_syset_client`: validated published native object addresses. Older desc/variant diagnostic exports remain zero and are unused.

Status 3 establishes that the original callback returned; it does not assert native parsing succeeded or that platform initialization completed. The original parser/OTF logs and downstream vehicle/HMI behavior must supply that runtime validation.

`verify.py` independently decodes every generated DSI record, verifies actual source payload equality and version preservation, confirms the five skip markers and exact stream end, and disassembles the init/apply entry points. `static-validation.txt` records the result. `build-manifest.json` records source/output/payload hashes and all imports. No guest VM has been started by this work.

The native event function pointer is held in a volatile local before the indirect call. This is necessary for an ELF ET_DYN preload: a compiler-optimized direct rel32 call to 0x08f99da0 would incorrectly acquire the provider's load bias. The fixed output at RVA 0x219b stores immediate 0x08f99da0, loads it into EAX at 0x21a3 and calls EAX at 0x21b2. `absolute-call-validation.txt` records the audit. The build now rejects every direct call whose target lies outside the provider DSO. The prior failing output is retained in `history/early-capture-direct-call`.
