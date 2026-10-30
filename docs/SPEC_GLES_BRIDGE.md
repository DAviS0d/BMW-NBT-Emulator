# Specificație: puntea GLES/EGL NBT (bibliotecă guest + transport + renderer Windows)

Stare: specificație pentru o reimplementare „clean-room”. Data: 2026-10-30.

Documentul descrie **comportamentul observabil și interfețele** perechii de producție
curente (biblioteca guest `libnbtgl.so` din varianta DMA și renderer-ul Windows
`nbt-glhost-dma*.exe`, cu comportamentul îmbunătățit al variantei „fast”). Este scris
astfel încât un inginer care nu a văzut codul vechi să poată construi o înlocuire
compatibilă octet cu octet (aceleași răspunsuri GL, aceiași pixeli, aceleași marcaje în
loguri). Nu conține cod, structuri C sau nume interne; conține doar fapte de interfață:
simboluri Khronos exportate, opcode-uri și formate de payload, offseturi din memoria
partajată, registre virtio/PCI, adrese din binarul BMW, variabile de mediu, nume de
fișiere și șiruri exacte pe care alte unelte le caută.

Convenții:

- Toate întregii de pe fir și din regiunea DMA sunt **little-endian**, 32 de biți, dacă nu
  se spune altfel. `u32` = fără semn, `i32` = cu semn, `f32` = biții brut ai unui float IEEE-754.
- Excepție: pachetele de pe portul de intrare (MTP / tastatură) au câmpuri **big-endian**.
- „Octeți” = bytes. „KiB/MiB” = 1024 / 1024².
- Șirurile marcate `așa` trebuie reproduse exact (inclusiv spațiile; `\n` = LF).
- Constante GL/EGL sunt date în hex, cu numele Khronos între paranteze.

---

## 1. Prezentare generală

### 1.1 Componente

```
 QNX 6.5 (VM QEMU, i386)                                Windows (host)
 ┌──────────────────────────────────────┐
 │ HmiMain3D (firmware BMW, nemodificat)│
 │   │ apeluri EGL/GLES/KD (ABI i386)   │
 │   ▼                                  │
 │ libnbtgl.so  (LD_PRELOAD)            │
 │   ├─ înregistrări GL ──► inel DMA TX ├──(memorie fizică guest, citită/scrisă
 │   │                ◄── inel DMA RX   │    de renderer cross-process)──┐
 │   ├─ bootstrap op 144 ─► virtio port1├─► chardev socket "glbridge" ──► nbt-glhost-dma*.exe
 │   │                     "nbtgl"      │    (TCP localhost)              │  (ANGLE, D3D)
 │   └─ fir MTP ◄─► virtio port2        ├─► chardev socket "nbtinput" ◄──► session.py
 │        "nbtinput"   │                │                                 │
 │        ▼ TCP 127.0.0.1:50123         │                                 └─► frame.ppm ─► viewer.py
 │      mtp2most (firmware)             │
 │      + coada nativă de tastatură HMI │
 └──────────────────────────────────────┘
```

1. **Biblioteca guest `libnbtgl.so`** — bibliotecă partajată ELF i386 încărcată prin
   `LD_PRELOAD` în procesul `HmiMain3D`. Exportă API-ul EGL 1.4 / GLES 2.0 (plus extensii
   folosite de firmware), serializează apelurile în „înregistrări” și le trimite
   renderer-ului; pentru apelurile care întorc valori, așteaptă răspunsul. În aceeași
   bibliotecă se află și driverul virtio-console (userspace, legacy PCI), inelul DMA și
   firul de intrare (MTP + HAL de tastatură).
2. **Transporturi**
   - *virtio-serial legacy PCI* (QEMU `virtio-serial-pci`, `disable-modern=on`), cu
     MULTIPORT: coada de control (2/3), portul 1 `nbtgl` (cozi 4/5) și portul 2
     `nbtinput` (cozi 6/7). Portul 1 transportă **doar** handshake-ul DMA (op 144) și
     confirmarea lui; portul 2 transportă fluxul MTP de intrare.
   - *Regiunea DMA* de 135168 de octeți, alocată de guest în memorie fizică contiguă, cu
     două inele de 64 KiB (comenzi guest→host, răspunsuri host→guest). Renderer-ul o
     accesează direct în memoria procesului QEMU.
3. **Renderer-ul Windows** `nbt-glhost-dma*.exe` — proces Windows x86-64 care se conectează
   la chardev-ul QEMU, atașează regiunea DMA, execută înregistrările cu ANGLE (EGL pbuffer,
   context GLES 2), trimite răspunsurile și publică fiecare cadru prezentat ca fișier PPM.
4. **Consumatori** — `run_hmi.py` (pornește QEMU + renderer, scrie configul DMA),
   `native_socket_bridge.py` (gestionează procesul renderer), `viewer.py` (afișează PPM-ul),
   `session.py` (trimite intrarea), teste de paritate și scripturi de performanță. Ei
   depind de marcajele de log descrise în §8.

### 1.2 Fluxul de pornire (rezumat)

1. `run_hmi.py` pornește QEMU (chardev `glbridge` server cu `wait=on`, deci VM-ul nu
   pornește până nu se conectează renderer-ul) și apoi renderer-ul cu
   `GLHOST_QEMU_PORT`. Renderer-ul se conectează și scrie
   `GLHOST_NATIVE_SOCKET_CONNECTED port=<n>`.
2. `run_hmi.py` află prin QMP adresa host a `pc.ram` și scrie fișierul de config DMA
   (`GLHOST_DMA_CONFIG`).
3. În guest, primul apel GL dintr-un fir (de regulă `eglInitialize`) inițializează
   dispozitivul virtio, face handshake-ul de control, pornește firul MTP, alocă regiunea DMA
   și trimite op 144 pe portul 1. Renderer-ul validează și răspunde cu `1` pe același
   canal; de acum toate înregistrările GL trec prin inelele DMA.

---

## 2. Biblioteca guest `libnbtgl.so`

### 2.1 Construire și ABI (obligatoriu)

| Element | Valoare cerută |
| --- | --- |
| Format | ELF32 i386, bibliotecă partajată, PIC |
| Toolchain folosit azi | `zig cc` 0.15.2 (`work/graphics-port/toolchain/zig-x86_64-windows-0.15.2/zig.exe`) |
| Țintă | `-target x86-linux-gnu -mcpu=pentium4` (ELF i386 generic; QNX 6.5 îl încarcă prin `ldqnx`) |
| Stivă | `-mstackrealign` (obligatoriu: firmware-ul nu garantează alinierea de 16 a stivei; și funcțiile din firmware apelate de HAL cer asta) |
| Mediu | `-ffreestanding -fno-builtin -fno-stack-protector -nostdlib -fPIC -O2 -shared` |
| Linker | `-Wl,--hash-style=sysv` (ldqnx nu înțelege `DT_GNU_HASH`), `-Wl,-z,norelro`, `-Wl,-soname,libnbtgl.so` |
| DT_NEEDED | niciunul; simbolurile importate se rezolvă din libc/libsocket deja încărcate în `HmiMain3D` |
| Helperi compilator | `memcpy`/`memset` și helperii aritmetici trebuie să fie furnizați static (cum face compiler-rt-ul zig); nu apar în lista de importuri |
| Destructor | trebuie să existe un simbol exportat `_fini` (linkerul îl folosește ca `DT_FINI`); comportament în §2.12 |
| Nume fișier | `libnbtgl.so` (instalat în IFS ca `/boot/lib/...` de builder-ul de IFS existent) |

**Importuri dinamice permise** (setul actual, exact): `atoi`, `usleep`, `mem_offset64`,
`abort`, `pthread_getspecific`, `pthread_setspecific`, `pthread_key_create`, `pthread_self`,
`pthread_create`, `pthread_join`, `send`, `getpid`, `read`, `write`, `close`, `fflush`,
`socket`, `connect`, `setsockopt`, `select`, `strcmp`, `strlen`, `__get_errno_ptr`, `malloc`,
`realloc`, `free`, `printf`, `vsnprintf`, `mmap64`, `ClockTime`, `getenv`, `ThreadCtl`.
O implementare nouă poate importa un subset, dar nu simboluri care lipsesc din libc /
libsocket QNX 6.5.

Fapte QNX folosite (API, nu cod): `ThreadCtl(_NTO_TCTL_IO=1, 0)` pentru privilegii I/O;
`mmap64(0, n, PROT_READ|PROT_WRITE = 0x300, MAP_SHARED|MAP_PHYS|MAP_ANON = 0x90001, NOFD=-1, 0)`
alocă memorie fizic contiguă; `mem_offset64(ptr, NOFD, n, &phys, &contig)` dă adresa
fizică; `ClockTime(CLOCK_MONOTONIC=2, NULL, &ns)` și `ClockTime(CLOCK_REALTIME=0, …)`.
Toate mesajele de diagnostic ale bibliotecii (cu excepția celor marcate „fd 2”) merg cu
`printf` pe stdout-ul procesului (consola QNX → `serial_com1.log`) și **fiecare linie este
urmată de `fflush`**, fiindcă alte unelte urmăresc fișierul serial în timp real.

**Exporturi**: exact 249 de simboluri dinamice: toate funcțiile din tabelele §2.6–§2.11
plus `_fini`. Builder-ul vechi verifică egalitatea setului de simboluri exportate cu
varianta anterioară; noua bibliotecă trebuie să exporte același set (nici mai mult, nici
mai puțin), cu signaturile C Khronos.

### 2.2 Modelul de înregistrare (record framing)

Fiecare apel GL/EGL „trimis” produce, în fluxul guest→host, **două înregistrări lipite**:

| Offset | Mărime | Conținut |
| --- | --- | --- |
| 0 | 4 | `119` (opcode „selectează clientul”) |
| 4 | 4 | `4` (lungimea payload-ului) |
| 8 | 4 | PID-ul procesului guest (`getpid()`) |
| 12 | 4 | opcode-ul apelului |
| 16 | 4 | `L` = lungimea payload-ului apelului |
| 20 | L | payload-ul apelului |

Deci fiecare apel are un prefix fix de 20 de octeți. Excepție unică: op 144 (§4.4), trimis
o singură dată, fără prefixul 119, pe virtio.

Reguli:

- `L` maxim admis de guest: 16 MiB (16·1024·1024). Peste → `abort()`.
- Înregistrarea se construiește complet într-un buffer **al firului curent** (thread-local),
  apoi se predă transportului atomic (§2.3). Dacă un apel declară `L` și ar adăuga mai
  mulți octeți decât `L` → `abort()`.
- Opcode-urile pentru care guest-ul **așteaptă răspuns** (marcate „sincron”): 100–109,
  120, 121, 123, 124, 126, 127, 131, 132, 134–138, 141, 142. (Biblioteca de producție emite
  efectiv doar 100–109, 120, 123, 124, 138, 141, 142; celelalte sunt rezervate altor variante
  și trebuie tratate la fel dacă vor fi emise.)

### 2.3 Fire de execuție, blocare, batching, flush

- **Stare per fir**: buffer-ul de înregistrare, legătura curentă `GL_ARRAY_BUFFER`
  (0x8892), legătura `GL_ELEMENT_ARRAY_BUFFER` (0x8893) și starea a 16 atribute de vârf
  (size, type, normalized, stride, buffer, enabled, pointer) sunt păstrate **per fir**
  (cheie TLS creată o singură dată, thread-safe; eliberată la ieșirea firului). Starea
  inițială e zero.
- **Contor de nume** global per proces, atomic, pornind de la 0; fiecare nume nou e
  „contor+1” (primul nume = 1). Același contor e folosit pentru shadere, programe, buffere,
  texturi, framebuffere și renderbuffere.
- **Lacăt global** (unul per proces) cu achiziție prin spin + `usleep(1000)` între
  încercări. Predarea unei înregistrări complete se face sub lacăt.
- **Batch de transmisie** de 65536 de octeți (o singură instanță per proces, folosită doar
  sub lacăt):
  - dacă înregistrarea (cu prefixul de 20 de octeți) are > 65536 octeți: se golește
    batch-ul și apoi înregistrarea se trimite direct;
  - altfel, dacă nu încape în spațiul rămas, se golește întâi batch-ul, apoi se adaugă;
  - batch-ul se golește imediat după adăugare dacă: înregistrarea e sincronă, sau opcode-ul
    e 5 (swap) sau 6 (finish/flush), sau batch-ul a ajuns exact plin.
- **Înregistrări sincrone**: după predare (care a golit batch-ul), lacătul **rămâne ținut**
  până când tot răspunsul a fost citit; abia apoi se eliberează. Astfel niciun alt fir nu
  poate intercala comenzi între cerere și răspuns. Înregistrările fără răspuns eliberează
  lacătul imediat după adăugare.
- **Flush fără inițializare**: `eglMakeCurrent`, `eglTerminate`, `eglDestroySurface`,
  `eglDestroyContext`, `eglReleaseThread`, `eglWaitGL`, `eglWaitNative` golesc batch-ul sub
  lacăt, dar **numai dacă** transportul e deja inițializat (nu declanșează inițializarea).
- **Inițializare leneșă** (prima trimitere dintr-un proces): fiecare fir care trimite cere
  o dată `ThreadCtl(_NTO_TCTL_IO)`; dacă eșuează scrie pe fd 2 exact cei 37 de octeți
  `glbridge: virtio I/O privilege failed` (fără LF; e o particularitate a vechii
  implementări) și face `abort()`. Inițializarea dispozitivului se face o singură dată
  (mașină de stări 0→1→2; ceilalți așteaptă cu `usleep(1000)`). Eșec →
  `glbridge: virtio init failed code=<n>` (printf + flush) și `abort()`. Codurile `<n>`:

| Cod | Cauză |
| --- | --- |
| 1 | `ThreadCtl` I/O eșuat |
| 2 | dispozitivul virtio-console legacy nu a fost găsit (`VIRTIO_PCI_DEVICE_NOT_FOUND` tipărit anterior) |
| 3 | BAR0 nu e spațiu I/O valid |
| 4 | cozile 4/5 nu s-au putut inițializa |
| 5 | bufferele de date 64 KiB ale portului 1 nu s-au alocat |
| 6 | statusul final al dispozitivului ≠ 7 |
| 7 | gazda nu oferă MULTIPORT |
| 8 | cozile de control 2/3 sau bufferele lor |
| 9 | handshake-ul de control a eșuat |
| 10 | cozile 6/7 (MTP) sau bufferele lor |
| 11 | firul MTP nu a pornit |
| 12 | bootstrap-ul DMA (op 144) a eșuat |

### 2.4 Secvența de inițializare a transportului (guest)

Ordinea este normativă (influențează ce vede QEMU și ce apare în log):

1. `ThreadCtl` I/O.
2. Scanare PCI prin mecanismul de configurare #1 (porturile `0xCF8`/`0xCFC`), magistrala 0,
   slot 0–31, funcția 0–7, adresă `0x80000000 | slot<<11 | fn<<8`; se caută dword-ul de la
   registrul 0 egal cu `0x10031AF4` (vendor 0x1AF4, device 0x1003 = virtio-console legacy).
   Negăsit → `VIRTIO_PCI_DEVICE_NOT_FOUND`.
3. Se tipărește `VIRTIO_PCI address=<hex> bar0=<hex> command=<hex>` (registrele 0x10 și 0x04).
   BAR0 trebuie să aibă bitul 0 setat, baza (`bar & ~3`) nenulă și < 65536.
4. Registrul de comandă PCI := (comanda curentă & 0xFFFF) | 0x405 (I/O space, bus master,
   INTx dezactivat). Driverul funcționează **numai prin polling**, fără întreruperi.
5. Registre legacy virtio (offset față de baza I/O): 0 = host features (32), 4 = guest
   features (32), 8 = queue PFN (32), 12 = queue size (16), 14 = queue select (16),
   16 = queue notify (16), 18 = device status (8), 19 = ISR (8).
   Status := 0, apoi 1, apoi 3. Se tipărește `VIRTIO_FEATURES host=<hex>`. Dacă bitul 1
   (MULTIPORT) lipsește → `VIRTIO_MULTIPORT_UNAVAILABLE`. Guest features := 2.
6. Inițializare cozi, în ordinea: 4, 5 (port 1 RX/TX), 2, 3 (control RX/TX) + două buffere
   de 4096 octeți, 6, 7 (port 2 RX/TX) + două buffere de 65536 octeți, cu un buffer RX
   postat imediat pe coada 6; apoi două buffere de 65536 octeți pentru coada 4/5 și un buffer
   RX postat pe coada 4.
7. Status := 7 (ACK|DRIVER|DRIVER_OK); notify pe coada 4 și pe coada 6.
8. Handshake de control (§4.2).
9. Pornește firul MTP (§3).
10. Bootstrap DMA (§4.4).
11. Se tipărește `VIRTIO_DRIVER_READY status=<n> vfast_io=<hex>`; succes dacă status = 7.

Alocare memorie DMA (pentru cozi, buffere și regiunea DMA): memorie fizic contiguă,
zeroizată, cu adresa fizică < 4 GiB, aliniată la pagină și contiguă pe toată lungimea.
La fiecare alocare se tipărește
`VIRTIO_DMA_ALLOC n=<k> virtual=<ptr> physical=<hex> bytes=<n> contiguous=<n> rc=<rc>`;
eșecul mmap tipărește `VIRTIO_DMA_MMAP_FAIL bytes=<n>`.

### 2.5 Funcții EGL

Notă: handle-urile EGL întoarse sunt valori fixe (`(void*)1`); există un singur display,
o singură configurație, un singur context și o singură suprafață pbuffer din punctul de
vedere al guest-ului. Eroarea EGL e o variabilă per proces, inițial `0x3000` (EGL_SUCCESS).

| Funcție (signatură Khronos) | Comportament | Trimite |
| --- | --- | --- |
| `EGLDisplay eglGetDisplay(EGLNativeDisplayType)` | întoarce 1 | — |
| `EGLDisplay eglGetPlatformDisplay(EGLenum, void*, const EGLAttrib*)` | întoarce 1 | — |
| `EGLBoolean eglInitialize(EGLDisplay, EGLint *major, EGLint *minor)` | scrie 1 / 4 dacă pointerii nu sunt NULL; citește `GLBRIDGE_W`, `GLBRIDGE_H` (atoi; lipsă sau ≤0 → 800 respectiv 480); întoarce 1 | op 1 `[w i32, h i32]`, la **fiecare** apel |
| `eglGetConfigs(dpy, configs, size, num)` | dacă `configs` ≠ NULL și `size` > 0 → `configs[0]=1`; `*num=1` dacă ≠ NULL; întoarce 1 | — |
| `eglChooseConfig(dpy, attrs, configs, size, num)` | identic cu `eglGetConfigs` (atributele se ignoră) | — |
| `eglGetConfigAttrib(dpy, cfg, attr, value)` | scrie valoarea din tabelul de mai jos (necunoscut → 0); întoarce mereu 1 | — |
| `eglCreateWindowSurface(...)` | ferestre native nesuportate în această variantă: eroare `0x300B` (BAD_NATIVE_WINDOW), scrie pe fd 2 `NBT native window not implemented\n`, întoarce NULL | — |
| `eglCreatePbufferSurface(...)` | întoarce 1 | — |
| `eglCreateContext(...)` | întoarce 1 | — |
| `eglMakeCurrent(...)` | flush fără inițializare (§2.3); întoarce 1 | — |
| `eglQuerySurface(dpy, surf, attr, value)` | lățime/înălțime din `GLBRIDGE_W/H` (implicit 800×480); dacă handle-ul `surf` > 1, citește lățimea și înălțimea ca doi `u32` de la adresa handle-ului (rămășiță pentru ferestre native); ≤0 → 800/480. `0x3057` (WIDTH) → w, `0x3056` (HEIGHT) → h, altceva → 0. Scrie dacă `value` ≠ NULL; întoarce 1 | — |
| `eglSwapBuffers(dpy, surf)` | trimite swap; apoi contorii de performanță (§2.13); întoarce 1 | op 5, L=0 (flush) |
| `eglSwapInterval` | întoarce 1 | — |
| `EGLint eglGetError(void)` | întoarce eroarea curentă și o resetează la `0x3000` | — |
| `eglTerminate`, `eglReleaseThread`, `eglWaitGL`, `eglWaitNative(EGLint)` | flush fără inițializare; întoarce 1 | — |
| `eglDestroySurface`, `eglDestroyContext` | flush fără inițializare; întoarce 1 | — |
| `EGLBoolean eglBindAPI(EGLenum)` | numai `0x30A0` (OPENGL_ES_API) acceptat → 1; altfel eroare `0x300C`, întoarce 0 | — |
| `EGLenum eglQueryAPI(void)` | `0x30A0` | — |
| `eglQueryContext(dpy, ctx, attr, value)` | dacă vreun argument e NULL: eroare `0x3006`, 0. `0x3028`→1, `0x3097`→0x30A0, `0x3098`→2, `0x3086`→`0x3084`; altfel eroare `0x3004`, 0; altfel 1 | — |
| `eglSurfaceAttrib(dpy, surf, attr, value)` | dpy/surf NULL → `0x300D`, 0; `attr=0x3093` cu `value=0x3095` → 1; altfel `0x3004`, 0 | — |
| `EGLBoolean eglWaitClient(void)` | apelează `glFinish` (op 6); întoarce 1 | op 6 |
| `eglBindTexImage`, `eglReleaseTexImage` | eroare `0x3009`, întoarce 0 | — |
| `eglCopyBuffers` | eroare `0x300A`, 0 | — |
| `eglCreatePixmapSurface` | eroare `0x300A`, NULL | — |
| `eglCreatePbufferFromClientBuffer` | eroare `0x3009`, NULL | — |
| `const char *eglQueryString(dpy, name)` | `0x3055` (EXTENSIONS) → `EGL_KHR_image EGL_KHR_image_base EGL_NV_system_time ` (cu spațiu final); orice altceva → `glshim-fwd` | — |
| `EGLuint64NV eglGetSystemTimeFrequencyNV(void)` | 1000000000 | — |
| `EGLuint64NV eglGetSystemTimeNV(void)` | nanosecunde `CLOCK_MONOTONIC` din QNX; eșec `ClockTime` → `abort()` | — |
| `eglGetCurrentDisplay`, `eglGetCurrentContext`, `eglGetCurrentSurface(EGLint)` | întorc 1 | — |
| `EGLImageKHR eglCreateImageKHR(...)` | eroare `0x300C`, NULL | — |
| `EGLBoolean eglDestroyImageKHR(...)` | eroare `0x300C`, 0 | — |
| `void *eglGetProcAddress(const char*)` | vezi §2.9 | — |
| `void NvEglRegClientApi(unsigned api, void *unused)` | nu face nimic (hook NVIDIA cerut de firmware) | — |

Valorile `eglGetConfigAttrib`: `0x3021`–`0x3024` (ALPHA/BLUE/GREEN/RED_SIZE) → 8;
`0x3020` (BUFFER_SIZE) → 32; `0x3025` (DEPTH) → 24; `0x3026` (STENCIL) → 8; `0x3028`
(CONFIG_ID) → 1; `0x302E` (NATIVE_VISUAL_ID) → 1; `0x302F` (NATIVE_VISUAL_TYPE) → 0;
`0x3033` (SURFACE_TYPE) → 5; `0x3040` (RENDERABLE_TYPE) → 0x44; `0x3042` (CONFORMANT) →
0x44; `0x303F` (COLOR_BUFFER_TYPE) → `0x308E`; `0x3027` (CONFIG_CAVEAT) → `0x3038`; orice
altceva → 0.

### 2.6 Funcții GLES trimise renderer-ului

Coloana „Payload” enumeră câmpurile în ordine, fiecare de 4 octeți, dacă nu se spune
altfel. „sincron” = guest-ul așteaptă răspunsul indicat (dimensiune exactă în octeți) și
îl consumă integral. Toate trimiterile poartă prefixul §2.2.

| Op | Funcție(i) | Payload | Răspuns / consum |
| --- | --- | --- | --- |
| 2 | `glViewport(x,y,w,h)` | x, y, w, h (i32) | — |
| 3 | `glClearColor(r,g,b,a)` | 4 × f32 | — |
| 4 | `glClear(mask)` | mask | — |
| 6 | `glFinish()`, `glFlush()` | L=0 | — (forțează golirea batch-ului) |
| 7 | `GLuint glCreateShader(type)` | id nou, type | — ; întoarce id-ul nou |
| 8 | `glShaderSource(sh, count, str, len)` | sh, T, apoi T octeți = concatenarea șirurilor | — . Lungimea fiecărui șir = `len[i]` dacă `len`≠NULL și `len[i]`≥0, altfel `strlen`; T = suma; fără terminator NUL |
| 9 | `glCompileShader(sh)` | sh | — |
| 10 | `GLuint glCreateProgram()` | id nou | — ; întoarce id-ul |
| 11 | `glAttachShader(p, s)` | p, s | — |
| 12 | `glLinkProgram(p)` | p | — |
| 13 | `glUseProgram(p)` | p | — |
| 14 | `glBindAttribLocation(p, idx, name)` | p, idx, n=strlen, n octeți nume (fără NUL) | — |
| 15 | `glGenBuffers(n, ids)` | n, apoi n id-uri noi | — ; dacă `ids` NULL nu face nimic; id-urile se scriu în `ids` |
| 16 | `glBindBuffer(target, id)` | target, id | — ; actualizează legătura per fir pentru 0x8892/0x8893 |
| 17 | `glBufferData(target, size, data, usage)` | target, S, usage, apoi S octeți dacă `data`≠NULL | — . S = size (negativ → 0). Dacă `data` NULL, payload-ul are 12 octeți |
| 18 | `glBufferSubData(target, off, size, data)` | target, off, S, apoi S octeți dacă `data`≠NULL | — |
| 19 | `glVertexAttribPointer(i, size, type, norm, stride, ptr)` | i, size, type, norm (0/1), stride, ptr (ca offset u32) | — ; vezi §2.10 (poate să nu se trimită nimic) |
| 20 | `glEnableVertexAttribArray(i)` | i | — ; marchează atributul activ per fir (dacă i<16) |
| 21 | `glDisableVertexAttribArray(i)` | i | — ; marchează inactiv |
| 22–25 | `glUniform{1,2,3,4}fv(loc, count, v)` | loc, count, count·k f32 (k=1..4) | — |
| 23 / 24 / 25 | `glUniform2f`, `glUniform3f`, `glUniform4f` | ca forma `fv` cu count = 1 | — |
| 26–28 | `glUniformMatrix{2,3,4}fv(loc, count, transpose, v)` | loc, count, transpose (valoarea brută), count·k² f32 | — |
| 29 | `glUniform1f(loc, v)` | loc (i32), v (f32) | — |
| 30 | `glUniform1i(loc, v)` | loc, v | — |
| 31 | `glDrawArrays(mode, first, count)` | mode, first, count | — ; vezi §2.10 |
| 32 | `glDrawElements` cu EBO legat | mode, count, type, offset | — ; vezi §2.10 |
| 33 / 34 | `glEnable(cap)` / `glDisable(cap)` | cap | — |
| 35 | `glBlendFunc(s, d)` | s, d | — |
| 36 | `glDepthFunc(f)` | f | — |
| 37 | `glCullFace(m)` | m | — |
| 38 | `glFrontFace(m)` | m | — |
| 39 | `glDepthMask(flag)` | flag (valoare brută) | — |
| 40 | `glClearDepthf(d)` | f32 | — |
| 42 | `glLineWidth(w)` | f32 | — |
| 43 | `glPolygonOffset(f, u)` | 2 × f32 | — |
| 50 | `glGenTextures(n, ids)` | n, n id-uri noi | — (NULL → nimic) |
| 51 | `glBindTexture(target, id)` | target, id | — |
| 52 | `glTexImage2D(target, level, ifmt, w, h, border, fmt, type, data)` | target, level, ifmt, w, h, border, fmt, type, S, apoi S octeți | — ; S conform regulii de mai jos, 0 dacă `data` NULL |
| 53 | `glTexParameteri(target, pname, param)` | target, pname, param | — |
| 54 | `glActiveTexture(t)` | t | — |
| 55 | `glPixelStorei(pname, param)` | pname, param | — |
| 56 | `glTexSubImage2D(target, level, x, y, w, h, fmt, type, data)` | target, level, x, y, w, h, fmt, type, S, apoi S octeți | — |
| 57 | `glGenerateMipmap(target)` | target | — |
| 58 | `glTexParameterf(target, pname, param)` | target, pname, f32 | — |
| 60 | `glBindFramebuffer(target, id)` | target, id | — |
| 61 | `glBindRenderbuffer(target, id)` | target, id | — |
| 62 | `glFramebufferTexture2D(target, att, textarget, id, level)` | 5 câmpuri | — |
| 63 | `glRenderbufferStorage(target, fmt, w, h)` | 4 câmpuri | — |
| 64 | `glFramebufferRenderbuffer(target, att, rbtarget, id)` | 4 câmpuri | — |
| 65 | `glScissor(x, y, w, h)` | 4 câmpuri | — |
| 66 | `glColorMask(r, g, b, a)` | 4 câmpuri (valori brute) | — |
| 67 | `glClearStencil(s)` | s | — |
| 68 | `glStencilMask(m)` | m | — |
| 69 | `glStencilFunc(func, ref, mask)` | 3 câmpuri | — |
| 70 | `glStencilOp(fail, zfail, pass)` | 3 câmpuri | — |
| 71 | `glBlendFuncSeparate(sr, dr, sa, da)` | 4 câmpuri | — |
| 72 | `glBlendEquation(m)` | m | — |
| 73 | `glBlendEquationSeparate(rgb, a)` | 2 câmpuri | — |
| 75 | `glStencilMaskSeparate(face, mask)` | 2 câmpuri | — |
| 76 | `glStencilFuncSeparate(face, func, ref, mask)` | 4 câmpuri | — |
| 77 | `glStencilOpSeparate(face, fail, zfail, pass)` | 4 câmpuri | — |
| 78 | `glGenFramebuffers(n, ids)` | n, n id-uri noi | — (n<0 sau NULL → nimic) |
| 79 | `glGenRenderbuffers(n, ids)` | n, n id-uri noi | — (idem) |
| 80–83 | `glUniform{1,2,3,4}iv(loc, count, v)` | loc, count, count·k i32 | — (count<0 → nimic) |
| 81 / 82 / 83 | `glUniform2i`, `glUniform3i`, `glUniform4i` | ca forma `iv` cu count = 1 | — |
| 84 | `glVertexAttrib{1,2,3,4}f`, `glVertexAttrib{1,2,3,4}fv` | index, x, y, z, w (f32) | — ; componentele lipsă completate cu (0, 0, 1) |
| 85 | `glDepthRangef(n, f)` | 2 × f32 | — |
| 86 | `glBlendColor(r, g, b, a)` | 4 × f32 | — |
| 87 | `glHint(target, mode)` | 2 câmpuri | — |
| 100 | `GLint glGetAttribLocation(p, name)` | p, n, n octeți nume | sincron, 4 (i32); valoare implicită −1 dacă citirea eșuează |
| 101 | `GLint glGetUniformLocation(p, name)` | idem | sincron, 4 |
| 102 | `glGetShaderiv(s, pname, out)` | s, pname | sincron, 4; scris în `out` dacă ≠ NULL |
| 103 | `glGetProgramiv(p, pname, out)` | p, pname | sincron, 4 |
| 104 | `glGetIntegerv(pname, out)` | pname | sincron, **64** (16 × i32); se copiază în `out` 4 valori pentru `0x0BA2`, `0x0C10`, `0x0C23`; 2 pentru `0x0D3A`; altfel 1. Eșec de citire → `out` neatins |
| 105 | `GLenum glGetError()` | L=0 | sincron, 4 |
| 106 | `glGetBooleanv(pname, out)` | pname | sincron, **16** octeți; se copiază 4 pentru `0x0C23`, altfel 1 |
| 107 | `glGetFloatv(pname, out)` | pname | sincron, **64** (16 × f32); se copiază 4 pentru `0x0C22`, `0x8005`; 2 pentru `0x0B70`, `0x846D`, `0x846E`; altfel 1 |
| 108 | `glGetShaderPrecisionFormat(st, pt, range, precision)` | st, pt | sincron, 12: range[0], range[1], precision; scrise dacă pointerii ≠ NULL |
| 109 | `GLenum glCheckFramebufferStatus(target)` | target | sincron, 4 |
| 110 | `glShaderBinary(count, shaders, format, binary, length)` | count, format, length, count id-uri, length octeți | — (count<0 sau length<0 → nimic) |
| 120 | `glReadPixels(x, y, w, h, fmt, type, pixels)` | x, y, w, h, fmt, type | sincron, w·h·4 octeți direct în `pixels`. Se trimite **doar** dacă 0<w≤2048, 0<h≤2048, fmt=`0x1908` (RGBA), type=`0x1401`, `pixels`≠NULL; altfel nu face nimic |
| 123 | `glGetActiveAttrib(p, i, bufSize, len, size, type, name)` | p, i, c | sincron: 12 octeți (length, size, type), apoi exact c octeți nume. c = min(bufSize, 4096); bufSize<0 → nimic trimis. Cei c octeți se copiază în `name` dacă ≠ NULL; length/size/type scrise dacă pointerii ≠ NULL |
| 124 | `glGetActiveUniform(...)` | idem | idem |
| 128 | (intern, §2.10) | index, size, type, norm, stride, B, apoi B octeți | — |
| 129 | (intern, §2.10) | mode, count, type, B, apoi B octeți indici | — |
| 130 | `glDeleteTextures` (tip 0), `glDeleteBuffers` (1), `glDeleteFramebuffers` (2), `glDeleteRenderbuffers` (3) | tip, n, n id-uri | — ; n≤0 sau `ids` NULL → nimic |
| 138 | (intern, §2.10) | count, type, offset | sincron, 4 (u32 index maxim) |
| 139 | `glCompressedTexImage2D(target, level, fmt, w, h, border, size, data)` | target, level, fmt, w, h, border, size, apoi size octeți dacă `data`≠NULL | — ; size<0 sau > 16 MiB − 28 → `abort()` |
| 140 | `glCopyTexSubImage2D(target, level, xo, yo, x, y, w, h)` | 8 câmpuri | — |
| 141 | `glGetVertexAttribiv(i, pname, out)` | i, pname | sincron, 16 (4 × i32); vezi §2.8 pentru valorile răspunse local |
| 142 | `GLboolean glIsEnabled(cap)` | cap | sincron, 4; întoarce 1 dacă ≠ 0 |
| 143 | `glSampleCoverage(value, invert)` | value (f32), invert (0/1) | — |

Regula de dimensiune S pentru op 52/56 (identică în guest; **nu ține cont de
`GL_UNPACK_ALIGNMENT`**): canale = 3 pentru fmt `0x1907` (RGB), 1 pentru `0x1909`
(LUMINANCE) și `0x1906` (ALPHA), 2 pentru `0x190A` (LUMINANCE_ALPHA), altfel 4;
octeți/pixel = canale, cu excepția tipurilor `0x8363`, `0x8033`, `0x8034` (565/4444/5551)
pentru care e 2; S = max(w,0) · max(h,0) · octeți/pixel.

Pentru `glDeleteBuffers`, înainte de trimitere guest-ul șterge din starea per fir orice
referință la id-urile șterse (legătura array/element devine 0; atributul care folosea
buffer-ul primește buffer 0 și pointer NULL).

### 2.8 Funcții răspunse local sau stub

| Funcție | Comportament |
| --- | --- |
| `glGetString(name)` | `0x1F00` → `glshim-fwd`; `0x1F01` → `glshim-fwd-renderer`; `0x1F02` → `OpenGL ES 2.0 (glshim-fwd)`; `0x8B8C` → `OpenGL ES GLSL ES 1.00`; `0x1F03` și orice altceva → șir gol |
| `glGetShaderInfoLog`, `glGetProgramInfoLog` | `*length=0` dacă ≠ NULL; `log[0]=0` dacă `log`≠NULL și bufSize>0; nu trimite nimic |
| `glDeleteShader`, `glDeleteProgram`, `glDetachShader` | nu fac nimic (shaderele/programele nu se distrug niciodată pe host) |
| `glClearDepth(double)` | nu face nimic (variantă desktop) |
| `glGetVertexAttribiv(i, pname, out)` | dacă i<16 și `out`≠NULL, răspunde local din starea per fir: `0x8622` ENABLED → enabled; `0x8623` SIZE → size sau 4 dacă 0; `0x8624` STRIDE → stride; `0x8625` TYPE → type sau `0x1406` dacă 0; `0x886A` NORMALIZED → 0/1; `0x889F` BUFFER_BINDING → id-ul buffer-ului (id guest). Altfel op 141; se copiază 4 valori pentru `0x8626` (CURRENT_VERTEX_ATTRIB), altfel 1 |
| `glEGLImageTargetTexture2DOES` | scrie pe fd 2 `NBT EGL image import not implemented\n` și `abort()` |
| 82 de funcții nesuportate (lista în Anexa A) | la **primul** apel al fiecăreia scrie pe fd 2 `glbridge: unsupported <nume>\n`; întotdeauna întoarce 0 (în EAX) și ignoră argumentele |

### 2.9 `eglGetProcAddress`

Compară exact (`strcmp`) numele cerut cu: **toate** funcțiile `gl*` exportate (inclusiv
stub-urile din Anexa A și `glEGLImageTargetTexture2DOES`) și următoarele funcții EGL:
`eglGetSystemTimeFrequencyNV`, `eglGetSystemTimeNV`, `eglCreateImageKHR`,
`eglDestroyImageKHR`, `eglBindAPI`, `eglChooseConfig`, `eglCreateContext`,
`eglCreatePbufferSurface`, `eglCreateWindowSurface`, `eglDestroyContext`,
`eglDestroySurface`, `eglGetConfigAttrib`, `eglGetConfigs`, `eglGetCurrentContext`,
`eglGetCurrentDisplay`, `eglGetCurrentSurface`, `eglGetDisplay`, `eglGetError`,
`eglGetPlatformDisplay`, `eglInitialize`, `eglMakeCurrent`, `eglQueryString`,
`eglQuerySurface`, `eglReleaseThread`, `eglSwapBuffers`, `eglSwapInterval`, `eglTerminate`,
`eglWaitGL`, `eglWaitNative`. Întoarce adresa funcției exportate corespunzătoare.

**Nu** sunt rezolvate (deși exportate): `eglGetProcAddress`, `eglQueryAPI`,
`eglQueryContext`, `eglSurfaceAttrib`, `eglWaitClient`, `eglBindTexImage`,
`eglReleaseTexImage`, `eglCopyBuffers`, `eglCreatePixmapSurface`,
`eglCreatePbufferFromClientBuffer`, `NvEglRegClientApi`, funcțiile `slog*`.

Nume nerezolvat → scrie pe fd 2 `glbridge: unresolved EGL procedure: <nume>\n` și întoarce
NULL.

### 2.10 Atribute de vârf în memoria clientului și desenare

Starea per fir a celor 16 atribute (§2.3) permite atribute „client-side” (fără VBO).

**`glVertexAttribPointer(i, size, type, norm, stride, ptr)`**: dacă i ≥ 16, size ∉ 1..4 sau
stride < 0 → `abort()`. Se memorează (size, type, norm, stride, ptr) și buffer = legătura
`GL_ARRAY_BUFFER` curentă a firului. Dacă buffer = 0 **nu se trimite nimic** (datele se
copiază la desenare); altfel op 19.

**Mărimea scalarului** după tip: `0x1400`/`0x1401` → 1; `0x1402`/`0x1403` → 2;
`0x1404`/`0x1405`/`0x1406`/`0x140C` → 4; alt tip folosit la desenare → `abort()`.

**Încărcarea atributelor client pentru V vârfuri** (V>0): pentru fiecare index 0..15, în
ordine crescătoare, care este activ și are buffer = 0: element = size·scalar; pas = stride
dacă ≠ 0, altfel element; B = (V−1)·pas + element. Dacă pointerul e NULL sau
B > 16 MiB − 24 → `abort()`. Se trimite op 128 cu `[index, size, type, norm, stride (brut,
poate fi 0), B]` urmat de B octeți citiți de la pointer.

**`glDrawArrays(mode, first, count)`**: first<0, count<0 sau first+count > 0x7FFFFFFF →
`abort()`. Dacă count>0, încarcă atributele client pentru V = first+count. Trimite apoi
op 31 (și pentru count = 0).

**`glDrawElements(mode, count, type, indices)`**: count<0 sau type ∉ {`0x1401`, `0x1403`,
`0x1405`} → `abort()`. count = 0 → **nu se trimite nimic**.

- *Fără EBO legat în fir*: `indices` NULL sau count·mărime > 16 MiB − 16 → `abort()`. Dacă
  există vreun atribut client activ, se calculează maximul indicilor din memoria clientului
  (valoarea maximă `0xFFFFFFFF` → `abort()`) și se încarcă atributele pentru V = max+1.
  Apoi op 129 `[mode, count, type, B = count·mărime]` + B octeți de indici.
- *Cu EBO legat*: dacă există atribut client activ, se trimite op 138
  `[count, type, offset = (u32)indices]` și se așteaptă 4 octeți (indexul maxim calculat de
  host din EBO). Răspuns `0xFFFFFFFF` sau eroare de citire → `abort()`. Se încarcă
  atributele pentru V = max+1. Apoi op 32 `[mode, count, type, offset]`.

### 2.11 Exporturi de logging QNX

| Funcție | Comportament |
| --- | --- |
| `int vslogf(int code, int severity, const char *fmt, va_list)` | fmt NULL → −1. Formatează în max. 1023 de caractere (trunchiere), scrie pe fd 2 (reîncercând scrieri parțiale; eșec → −1); dacă mesajul e gol sau nu se termină cu LF, mai scrie un LF. Întoarce numărul de octeți ai mesajului (fără LF-ul adăugat). **Nu întoarceți 0 pentru un mesaj nevid** (dispecerul KD al firmware-ului reîncearcă la infinit octeții neconsumați) |
| `int slogf(int, int, const char *fmt, ...)` | identic, variadic |
| `slog2f`, `slog2c`, `slog2_register` | întorc 0, nu fac nimic |

### 2.12 Descărcare (`_fini`)

1. Cere oprirea firului MTP și îl așteaptă (join), dacă a fost pornit.
2. Dacă transportul e inițializat: încearcă **o singură dată**, fără așteptare, să ia
   lacătul global. Reușit → golește batch-ul, eliberează. Ocupat → scrie pe fd 2
   `NBT_BATCH_FINI_SKIPPED_BUSY\n` (nu așteaptă).
3. Dacă dispozitivul a fost găsit: status virtio := 0 (reset).

### 2.13 Marcaje de performanță la swap

La fiecare `eglSwapBuffers` se incrementează un contor de cadre; pentru cadrele 1, 2, 3 și
apoi fiecare multiplu de 30 se tipăresc (printf + flush):

- doar la cadrul 1: `NBT_VFAST_PERF_CONFIG loops_per_sleep=65536 timeout_iterations=800000000 profile=WHPX_ONLY`
- `NBT_VFAST_PERF_FRAME frame=<n> qnx_realtime_ns=<ns CLOCK_REALTIME> clock_rc=<rc>`
  (consumat de `benchmark_navigation.py` cu regex `NBT_VFAST_PERF_FRAME frame=(\d+) qnx_realtime_ns=(\d+)`)
- pentru fiecare coadă virtio 0..7 care a avut măcar o completare sau un timeout:
  `NBT_VFAST_PERF_QUEUE frame=<n> queue=<q> completed=<c> immediate=<i> spins=<s> sleeps=<z> max_spins=<m> timeouts=<t>`
  unde, pentru așteptările de completare virtio din §4.1: completed = completări reușite,
  immediate = completări găsite fără nicio iterație de așteptare, spins = total iterații,
  sleeps = Σ(iterații / 65536), max_spins = maximul iterațiilor unei așteptări,
  timeouts = așteptări expirate.

### 2.14 Ferestre native, WAL și cache-ul de cadre native

În varianta de producție, ferestrele/imaginile native **nu sunt implementate** în
bibliotecă: `eglCreateWindowSurface` eșuează (§2.5), `eglCreateImageKHR`/
`eglDestroyImageKHR` eșuează, `glEGLImageTargetTexture2DOES` oprește procesul.
Compozitorul WAL al firmware-ului randează în pbuffer-ul expus. Hook-urile interne
(creare/swap/distrugere fereastră, legare textură, înregistrare API) nu au efect.
Biblioteca de producție **nu emite** op 125 și 131–137; renderer-ul trebuie totuși să le
trateze ca în §5.8 (sunt folosite de alte variante guest).

---

## 3. Partea de intrare (în aceeași bibliotecă)

### 3.1 Firul MTP (portul virtio 2)

Firul este creat în pasul 9 din §2.4 și tipărește
`NBT_MTP_VIRTIO_WORKER_CREATED value=<id fir> errno=0 host_to_native=0 native_to_host=0`.
Toate diagnosticele acestui fir au forma exactă

`NBT_MTP_VIRTIO_<EVENIMENT> value=<i32> errno=<i32> host_to_native=<u64> native_to_host=<u64>`

(ultimele două sunt totalurile de octeți spre mtp2most, respectiv spre host). Creare eșuată
→ `THREAD_FAILED` și init cod 11.

Comportament:

1. Cere `ThreadCtl` I/O (eșec → `IO_PRIVILEGE_FAILED`, firul se termină).
2. Conectare TCP la `127.0.0.1:50123` (serverul `mtp2most` din firmware): până la 300 de
   încercări, la 100 ms una de alta, oprindu-se dacă s-a cerut stop; diagnostic
   `CONNECT_RETRY` (value = numărul încercării, errno = ultima eroare) la încercarea 1 și la
   fiecare a 25-a; eșec final → `CONNECT_FAILED value=300`. La succes se setează
   `TCP_NODELAY` (nivel 6, opțiune 1, valoare int 1) și se tipărește
   `NBT_MTP_VIRTIO_TCP_NODELAY fd=<fd> result=<r> errno=<e> value=1`, apoi
   `CONNECTED_127_0_0_1_50123` (value = fd).
3. fd ≥ 1024 → `FD_OUTSIDE_SELECT_SET`, termină.
4. Tipărește `BIDIRECTIONAL_READY_PORT2_50123` cu value = 2 (linia completă:
   `NBT_MTP_VIRTIO_BIDIRECTIONAL_READY_PORT2_50123 value=2 errno=0 …`; `session.py` caută
   subșirul `NBT_MTP_VIRTIO_BIDIRECTIONAL_READY`).
5. Buclă până la cererea de stop:
   - **host → nativ**: dacă coada 6 are un element „used” (verificare fără blocare): id
     trebuie 0 și lungime ≤ 65536, altfel `RX_DESCRIPTOR_INVALID` (value = id, câmpul errno =
     lungimea) și termină. Octeții se dau framer-ului (§3.2); eșecul lui termină firul.
     Bufferul RX se repostează **numai după** ce toți octeții au fost acceptați. Diagnostic
     `HOST_TO_NATIVE_CHUNK` (value = lungimea) pentru primele 8 bucăți și apoi când numărul
     de bucăți e putere a lui 2.
   - **nativ → host**: `select` cu timeout zero pe socket; dacă e citibil, `read` de până
     la 65536 octeți direct în bufferul TX al cozii 7, trimitere și așteptarea completării
     (eșec → `TX_COMPLETION_FAILED`). Diagnostic `NATIVE_TO_HOST_CHUNK` după aceeași regulă.
     `read` = 0 → `NATIVE_EOF`, termină. `read` < 0 → `READ_RETRY` la primul eșec consecutiv,
     după > 1000 consecutive `READ_FAILED` și termină. `select` < 0 → `SELECT_RETRY` /
     `SELECT_FAILED` (aceeași regulă).
   - Dacă iterația nu a progresat sau la fiecare a 64-a iterație: `usleep(1000)`.
6. La final închide socketul și tipărește `WORKER_STOPPED` (value = 1 dacă s-a cerut stop,
   altfel 0).

Trimiterea spre mtp2most: `send` neblocant (flag-uri QNX `MSG_DONTWAIT|MSG_NOSIGNAL` =
0x880) în buclă; la primul eșec `TCP_SEND_RETRY` (value = octeți trimiși), pauză 1 ms
între reîncercări; `send` = 0 sau > 2000 reîncercări → `TCP_SEND_FAILED` și eșec.

Oprirea (`_fini`) setează cererea de stop și face join; toate operațiile pe socket sunt
neblocante, deci join-ul se termină.

### 3.2 Framing-ul portului 2

Fluxul de pe portul 2 este o succesiune de pachete MTP. Fiecare pachet începe cu lungimea
**totală** a pachetului (inclusiv cei 2 octeți de lungime), big-endian u16. Fragmentele se
păstrează între bucăți, fără timeout. Buffer maxim: 4096 de octeți.

| Regulă | Rezultat |
| --- | --- |
| lungime < 7 sau > 4096 | `NBT_PORT2_FRAME_LENGTH_REJECTED length=<n>`; eșec (firul MTP se termină) |
| pachet complet cu octetul 2 = `0xFE` | pachet de tastatură emulată → §3.3 (nu ajunge la mtp2most) |
| pachet complet cu octetul 2 = `0x02` și lungime < 12 | `NBT_PORT2_MTP_HEADER_REJECTED length=<n>`; eșec |
| orice alt pachet complet | trimis neschimbat (octet cu octet, în ordine) la mtp2most |

Notă: pachetele `0xFC` (extensia DOOM din `session.py`) sunt, pentru această bibliotecă,
pachete MTP obișnuite și se trimit la mtp2most; tratarea lor aparține altei variante.

### 3.3 HAL-ul de tastatură (pachete `0xFE` / `0xFD`)

**Format pachet (8 octeți, câmpuri big-endian):**

| Octet | Câmp |
| --- | --- |
| 0–1 | lungime = 8 |
| 2 | tip: `0xFE` = cerere host→guest, `0xFD` = confirmare guest→host |
| 3 | versiune = 1 |
| 4 | cheie: 0 = interogare capabilitate; 1–12 = buton (push); 13 = rotire în jos (crescător), 14 = rotire în sus |
| 5 | pressed (0/1) — la confirmarea unei interogări: ready (0/1) |
| 6–7 | repeat (u16 BE): număr de detente la rotire |

Coduri folosite de `session.py`: menu 1, back 2, option 3, media 4, radio 5, tel 6, nav 7,
select 8, tilt_up 9, tilt_down 10, tilt_left 11, tilt_right 12, down 13, up 14.

**Validare** (orice încălcare → `NBT_KEYBOARD_PACKET_REJECTED length=<l> key=<k> pressed=<p> repeat=<r>`
și eșec, ceea ce **oprește firul MTP**): lungime = 8; octetul 3 = 1; pressed ≤ 1; cheia 0
cere pressed = 0 și repeat = 0; cheile 13/14 cer pressed = 0 și repeat în 1..64; cheile
1–12 cer repeat = 0; orice altă cheie e respinsă.

**Rezolvarea „sink”-ului nativ** (toate citirile sunt read-only; HAL-ul nu scrie nimic în
starea existentă a firmware-ului). Adresele sunt ale binarului `HmiMain3D` original, non-PIE
(SHA256 `554b67d4d6317cfb1715d544874fae8ddd2c975be503c9e2514e2dc2f3a0d693`). Convenție de
apel: cdecl i386 (argumente pe stivă, rezultat în EAX/AL; `this` = primul argument).

1. **Identitate**: cei 16 octeți de cod de la fiecare adresă trebuie să fie exact:
   - `0x080B45D8`: `55 89 E5 83 EC 08 80 3D 50 0F 8C 09 00 75 47 83`
   - `0x080B007E`: `55 89 E5 53 83 EC 04 8B 5D 08 83 BB C4 00 00 00`
   - `0x08A0A732`: `55 89 E5 83 EC 20 8B 45 08 8B 10 6A 0E 50 FF 52`
   - `0x080968A0`: `55 89 E5 56 53 0F B7 1D 8C 6D 90 09 C1 E3 10 81`

   Nepotrivire → `NBT_KEYBOARD_NATIVE_IDENTITY_FAILED`, sink indisponibil.
2. Octetul de la `0x098C0F50` (garda singleton-ului) ≠ 0 — altfel indisponibil (nu se
   apelează getter-ul leneș, care ar construi singleton-ul).
3. tip = u16 de la `0x09906D8C` ≠ 0 și u32 de la `0x09906D88` = `0x096218CA`.
4. legacy = apel `0x080B45D8()` (fără argumente) ≠ NULL.
5. Pointerul de la legacy + 0xC4 ≠ NULL (precondiție a getter-ului următor, care altfel
   asertează).
6. context = apel `0x080B007E(legacy)` ≠ NULL.
7. vtable(context) ≠ NULL și intrarea 4 (offset 0x10) ≠ NULL; candidat = acea funcție
   apelată cu (context, 0x0E) ≠ NULL.
8. proc = apel `0x08A0A732(context)`; trebuie ≠ NULL și egal cu candidatul.
9. vtable(proc) ≠ NULL și intrarea 7 (offset 0x1C) ≠ NULL → funcția `post(proc, event)`
   (întoarce un octet).
10. Tipul recitit de la `0x09906D8C` e egal cu cel de la pasul 3 → sink disponibil
    („queue_ready”).

**Pregătirea UI** (doar pentru interogarea cu cheia 0): cu funcția de la vtable(context)[4]:
display = (context, 0x1F), manager = (context, 0x25); enabled = octetul de la
display + 0x31 ≠ 0; handler = pointerul de la manager + 4; ready = queue_ready și enabled și
handler ≠ NULL.

**Cheia 0 (capabilitate)**: tipărește
`NBT_KEYBOARD_CAPABILITY ready=<0|1> queue_ready=<0|1> type=<u> context=<p> sink=<p> post=<p> display=<p> display_enabled=<u> input_manager=<p> input_handler=<p>`
și trimite confirmarea: copia pachetului cu octetul 2 = `0xFD` și octetul 5 = ready. Acest
caz nu eșuează din cauza lipsei de pregătire.

**Cheile 1–14 (eveniment)**:

1. Sink indisponibil → `NBT_KEYBOARD_NATIVE_QUEUE_NOT_READY key=<k> type=<t>`, eșec.
2. event = apel `0x080968A0()` (fabrica originală, fără argumente). NULL →
   `NBT_KEYBOARD_FACTORY_FAILED key=<k>`, eșec.
3. routing = u32 de la event + 4; trebuie (routing >> 16) = tip și u32 de la event + 0x0C = 0,
   altfel `NBT_KEYBOARD_NEW_EVENT_INVALID key=<k> routing=<hex> registered_type=<t>`, eșec.
4. Scrie în evenimentul nou: u32 cheia la +0x10, octet pressed la +0x14, octet 0 la +0x1C;
   **numai pentru rotire** u32 repeat la +0x18 (la butoane rămâne valoarea implicită a
   constructorului, 1). Citește valoarea de la +0x18 înainte de post (pentru log).
5. accepted = `post(proc, event)`. După post, evenimentul aparține cozii: nu se mai citește,
   nu se eliberează. accepted = 0 → `NBT_KEYBOARD_NATIVE_POST_FAILED key=<k> sink=<p> type=<t>`,
   eșec.
6. Contor de evenimente +1;
   `NBT_KEYBOARD_EVENT_POSTED number=<n> key=<k> pressed=<p> repeat=<valoarea +0x18> type=<t> sink=<p> post=<p>`;
   trimite confirmarea `0xFD` (copie a pachetului, octetul 5 neschimbat).

Confirmarea se trimite pe coada 7 (același fir, același buffer TX) și se așteaptă
completarea; eșec → `NBT_KEYBOARD_ACK_TX_FAILED key=<k>`. Octeții de confirmare se adaugă la
totalul „native_to_host”.

Consumatori: `session.py` consideră controlul configurat la prima confirmare `0xFD` cu
cheia 0 și octetul 5 = 1; `observe_keyboard.py`/`observe_home.py` caută
`NBT_KEYBOARD_CAPABILITY ready=1`; `test_buttons_runtime.py` extrage
`NBT_KEYBOARD_EVENT_POSTED number=\d+ key=(\d+) pressed=(\d)` și liniile
`NBT_KEYBOARD_(PACKET_REJECTED|NATIVE_QUEUE_NOT_READY|NATIVE_POST_FAILED)`.

---

## 4. Transport

### 4.1 Cozi virtio legacy (vring)

- Dimensiunea cozii n (citită după selectare) trebuie să fie putere a lui 2, nenulă,
  ≤ 32768.
- Așezare: descriptori 16·n octeți la 0; inelul „available” imediat după (flags u16,
  idx u16, n × u16, used_event u16); inelul „used” la următorul multiplu de 4096 după
  descriptori + available (flags u16, idx u16, n × {id u32, len u32}); mărimea totală
  rotunjită la 4096. Memoria se alocă zeroizată; avail.flags := 1 (fără întreruperi);
  PFN := adresa fizică >> 12. Se tipărește
  `VIRTIO_QUEUE index=<i> count=<n> bytes=<b> pfn=<hex> readback=<hex>`.
- Cozile de date (4, 5, 6, 7) folosesc **un singur buffer în zbor**, descriptorul 0
  (adresă, lungime, flags, next = 0); flags = 2 (WRITE) pentru RX, 0 pentru TX. Postare:
  scrie descriptorul, intrarea avail[submitted mod n] = 0, barieră, avail.idx = ++submitted,
  barieră, notify cu indexul cozii.
- Completare: polling pe used.idx ≠ completed, cu `pause`; după fiecare 65536 de iterații
  `usleep(1000)`; la 800 000 000 de iterații se tipărește
  `VIRTIO_WAIT_TIMEOUT queue=<q> submitted=<s> vfast_complete=<c> used=<u> status=<st> isr=<isr>`
  și se întoarce eroare. Elementul used citit trebuie să aibă id = 0.
- Coada de control RX folosește min(n, 16) sloturi de câte 256 de octeți (bufferul de 4096),
  descriptorul i ↔ slotul i, toate postate înainte de DRIVER_OK; un slot se repostează după
  ce mesajul a fost copiat integral.

### 4.2 Handshake-ul de control (virtio-console MULTIPORT)

Mesaj de control: 8 octeți = id port (u32), eveniment (u16), valoare (u16), urmați
opțional de un nume (PORT_NAME). Evenimente: 0 DEVICE_READY, 1 DEVICE_ADD, 2 DEVICE_REMOVE,
3 PORT_READY, 6 PORT_OPEN, 7 PORT_NAME.

- Trimitere: pe coada 3, cu așteptarea completării; după fiecare
  `VIRTIO_CONTROL_SEND id=<id> event=<e> value=<v>`.
- Recepție: polling pe coada 2 (după fiecare 4096 iterații `usleep(1000)`; la 50 000 000 de
  iterații `VIRTIO_CONTROL_TIMEOUT submitted=<s> complete=<c> used=<u>`); elementul trebuie
  să aibă id < numărul de sloturi și 8 ≤ lungime ≤ 256, altfel
  `VIRTIO_CONTROL_INVALID id=<id> length=<l>`. Numele = octeții de după primii 8, terminat
  cu NUL.

Secvență:

1. Trimite DEVICE_READY (id `0xFFFFFFFF`, eveniment 0, valoare 1).
2. Primește până la 128 de mesaje; pentru fiecare tipărește
   `VIRTIO_CONTROL_RECEIVE id=<id> event=<e> value=<v>`; ignoră porturile ≠ 1, 2.
   - DEVICE_ADD cu valoare ≠ 0, prima dată pentru port → trimite PORT_READY(id, 3, 1) și
     PORT_OPEN(id, 6, 1).
   - PORT_NAME: numele trebuie să fie `nbtgl` pentru portul 1 și `nbtinput` pentru portul 2,
     altfel `VIRTIO_CONTROL_WRONG_PORT_NAME id=<id> name=<n> expected=<e>` și eșec; la succes
     `VIRTIO_CONTROL_PORT_NAME id=<id> name=<n>`.
   - PORT_OPEN de la host: marchează portul deschis (valoare ≠ 0) sau închis.
   - DEVICE_REMOVE → `VIRTIO_CONTROL_PORT_REMOVED id=<id>`, eșec.
3. Când ambele porturi au fost: confirmate cu PORT_READY, numite și deschise de host →
   tipărește cele două linii (în această ordine):
   `VIRTIO_FLOW_CONTROLLED_PORT_READY id=1 rx_queue=4 tx_queue=5` și
   `VIRTIO_FLOW_CONTROLLED_PORT_READY id=2 rx_queue=6 tx_queue=7`; succes.
4. După 128 de mesaje fără succes → `VIRTIO_CONTROL_EVENT_LIMIT`, eșec.

Consecință: portul 2 este „deschis de host” numai după ce un client s-a conectat la
chardev-ul `nbtinput` (QEMU `server=on,wait=off`); inițializarea GL așteaptă deci și
conectarea sesiunii de intrare.

Configurația QEMU așteptată (din `run_hmi.py`): `virtio-serial-pci,id=vfast,disable-modern=on,disable-legacy=off,max_ports=3`,
`virtserialport,chardev=glbridge,bus=vfast.0,nr=1,name=nbtgl`,
`virtserialport,chardev=nbtinput,bus=vfast.0,nr=2,name=nbtinput`, ambele chardev-uri
`socket` pe `127.0.0.1` cu `nodelay=on` (`glbridge`: `server=on,wait=on`; `nbtinput`:
`server=on,wait=off`). Mașină `pc`, 512 MiB RAM (obligatoriu pentru DMA).

### 4.3 Regiunea DMA

Mărime totală 135168 de octeți (33 de pagini), alocată de guest ca memorie fizic contiguă,
aliniată la pagină, zeroizată. Toate offseturile sunt relative la începutul regiunii.

| Offset | Mărime | Conținut | Proprietar (cine scrie) |
| --- | --- | --- | --- |
| 0 | 16 | magic ASCII `NBT_DMA_RING_V2` + un octet NUL | guest (la init) |
| 16 | 4 | versiune = 2 | guest |
| 20 | 4 | mărime totală = 135168 | guest |
| 24 | 4 | capacitatea unui inel = 65536 | guest |
| 28 | 16 | nonce: PID guest, (adresa fizică XOR ns_low), ns_low, ns_high (ns = `CLOCK_MONOTONIC` la init) | guest |
| 44–63 | — | zero | — |
| 64 | 4 | „atașat”: host scrie 1 după validare | **host** |
| 68 | 4 | „stop”: host scrie 1 la terminare | **host** |
| 128 / 132 | 4 + 4 | TX head (octeți scriși de guest în total) + complement | guest |
| 192 / 196 | 4 + 4 | TX tail (octeți consumați de host) + complement | **host** |
| 256 / 260 | 4 + 4 | RX head (octeți de răspuns scriși de host) + complement | **host** |
| 320 / 324 | 4 + 4 | RX tail (octeți de răspuns consumați de guest) + complement | guest |
| 4096 | 65536 | inel TX (comenzi guest → host) | guest |
| 69632 | 65536 | inel RX (răspunsuri host → guest) | **host** |

Reguli ale contoarelor:

- Contoarele sunt cursoare libere pe 32 de biți (modulo 2³²); poziția în inel = cursor mod
  65536; ocupare = head − tail (modulo 2³²) și trebuie să fie ≤ 65536, altfel e eroare de
  protocol.
- **Publicare**: scrie valoarea, barieră, scrie complementul pe 32 de biți (`~valoare`) la
  offset + 4, barieră.
- **Citire validă**: citește valoarea, complementul, apoi din nou valoarea; validă numai dacă
  cele două citiri ale valorii sunt egale și complementul corespunde. O citire invalidă nu e
  eroare: înseamnă publicare în curs și se reîncearcă.
- Datele se copiază în inel **înainte** de publicarea cursorului; o copiere se oprește la
  capătul inelului (nu face wrap într-o singură copiere).
- La init guest-ul publică toate cele patru contoare cu 0 (deci complementele sunt
  `0xFFFFFFFF`).

### 4.4 Bootstrap-ul op 144 și confirmarea

După ce regiunea e inițializată (header + contoare), guest-ul copiază nonce-ul la offset 28
și trimite pe **coada 5 (portul 1, virtio)** un singur buffer de 36 de octeți:

| Offset | Câmp |
| --- | --- |
| 0 | 144 |
| 4 | 28 (lungimea payload-ului) |
| 8 | adresa fizică a regiunii (u32) |
| 12 | 135168 |
| 16 | 2 (versiune) |
| 20 | 16 octeți nonce (identici cu header-ul de la offset 28) |

Fără prefix 119. Guest-ul așteaptă completarea TX, apoi o completare pe coada 4 (RX) care
trebuie să aibă lungimea 4 și conținutul u32 = 1, **și** cuvântul de la offset 64 al regiunii
= 1. Orice altceva → eșec (cod 12). Apoi repostează bufferul RX al cozii 4, consideră DMA-ul
activ și tipărește
`NBT_DMA_TRANSPORT_READY physical=<hex> bytes=135168 capacity=65536 original_stream=1`
(consumat de `record_result.py` și `measure_owned_memory.py`, care extrage `physical=`).

De acum înainte **toate** înregistrările GL și toate răspunsurile trec exclusiv prin inele;
portul 1 nu mai e folosit pentru date. (Calea de date virtio pentru înregistrări GL nu este
necesară: dacă bootstrap-ul eșuează, procesul se oprește.)

### 4.5 Protocolul inelelor — partea guest

- **Trimitere** (guest → host): citește valid TX tail (192); ocupare = TX head local − tail
  (> 65536 → `abort()`); spațiu liber = 65536 − ocupare; copiază min(liber, până la capătul
  inelului, rămas) la 4096 + poziție; avansează head-ul local și îl publică la 128; repetă.
- **Recepție** (host → guest): citește valid RX head (256); disponibil = head − tail local
  (> 65536 → eroare); copiază min(disponibil, până la capăt, rămas) de la 69632 + poziție;
  avansează tail-ul local și îl publică la 320; repetă până la numărul cerut de octeți.
- **Așteptare** (când contorul e invalid sau nu există spațiu/date): la fiecare iterație
  verifică întâi cuvântul de stop (68): ≠ 0 → `NBT_DMA_HOST_STOPPED`, eșec; apoi `pause`;
  la fiecare 65536 de iterații citește ceasul monoton și, dacă au trecut > 10 s de la
  începutul așteptării curente, tipărește `NBT_DMA_WAIT_TIMEOUT` și eșuează, altfel
  `usleep(1000)`. Contorul de timp se resetează după orice progres.
- Eșec la trimitere → `abort()`. Eșec la recepție → apelul GL primește valoarea implicită
  (de ex. 0 pentru `glGetError`, −1 pentru locații), cu excepția op 138 (→ `abort()`).

### 4.6 Rezumat: ce înregistrări au răspuns

Renderer-ul răspunde exact la: 100–109 (110 nu), 120, 123, 124, 131, 132, 138, 141, 142, iar
la 144 pe socket. Dimensiunile răspunsurilor sunt în §5.8.

---

## 5. Renderer-ul Windows

### 5.1 Contractul procesului

| Element | Contract |
| --- | --- |
| Executabil | Windows x86-64, fără argumente în linia de comandă. Trebuie să poată înlocui direct `work/graphics-port/host/nbt-glhost-dma.exe` și `…/nbt-glhost-dma-fast.exe` (căile sunt fixate în `run_hmi.py`, `viewer.py`, `run_split.py`) |
| Director curent | directorul executabilului (setat de `native_socket_bridge.py`) |
| DLL-uri | `libEGL.dll` și `libGLESv2.dll` ANGLE din `work/graphics-port/host/angle/angle-x64/bin`, găsite prin `PATH` (bridge-ul pune acel director primul în `PATH`). Pentru pixeli identici trebuie folosite **exact aceste binare ANGLE** (proveniență în `host/angle-provenance.json`) și display-ul implicit |
| `GLHOST_QEMU_PORT` | port TCP zecimal 1..65535. Dacă e setat: modul socket (§5.2). Dacă lipsește/gol: stdin = flux de comenzi binar, stdout = răspunsuri (mod legacy stdio; recomandat de păstrat, nefolosit de producție) |
| `GLHOST_DMA_CONFIG` | calea fișierului de config DMA (§5.3). Lipsă/gol → op 144 primește ack 0 |
| `MHI2_GL_FRAME` | calea PPM-ului publicat; lipsă/gol → `nbt-frame.ppm` (relativ la directorul curent) |
| `MHI2_SHADER_CACHE` | directorul cu GLSL-uri pentru shaderele binare NVIDIA (§5.10); `run_hmi.py` folosește `work/graphics-port/host/shader-cache` |
| `MHI2_GL_CAPTURE` | opțional: fișier în care se scrie fiecare înregistrare primită (8 octeți header + payload), înainte de validare |
| `MHI2_GL_TRACE` | opțional: dacă există, scrie pe stderr `glhost op=<op> len=<len>` pentru fiecare înregistrare |
| `MHI2_GL_DUMP_CLIENTS` | opțional: dacă există, la fiecare swap publică și `nbt-client-<pid>.ppm` (director curent) |
| stdin | în modul socket: **numai** pipe de control al duratei de viață (conținutul se ignoră; EOF = oprire) |
| stdout | nefolosit în modul socket (bridge-ul îl leagă la DEVNULL) |
| stderr | log text, linie cu linie, **nebufferizat sau golit după fiecare linie** (consumatorii îl citesc în timp real) |

**Coduri de ieșire:**

| Cod | Situație |
| --- | --- |
| 0 | terminare normală: EOF/anulare, înregistrare invalidă, înregistrare > 64 MiB, eșec de scriere a unui răspuns, atașare DMA eșuată, atribut fără buffer (op 19) |
| 1 | eșec EGL la creare/activare, prea mulți clienți, alocare eșuată pentru un client sau pentru un atribut client |
| 2 | eșec la pornirea transportului socket |
| 3 | înregistrare video/encoder (122, 126, 127, 134–137) |
| 4 | shader binar NVIDIA necunoscut |
| 5 | înregistrare 139/140/141/142/143 cu lungime greșită (nu poate apărea după validare, dar se păstrează) |

`run_hmi.py` consideră orice cod ≠ 0 o defecțiune de infrastructură.

### 5.2 Canalul socket și semantica EOF/anulare

1. Inițializează Winsock 2.2 (eșec → `GLHOST_SOCKET_ERROR WSAStartup=<err>`, ieșire 2).
   Port invalid → `GLHOST_SOCKET_ERROR invalid GLHOST_QEMU_PORT`, ieșire 2.
2. Se conectează TCP la `127.0.0.1:<port>`; la eșec reîncearcă la 25 ms, timp de 10 s;
   eșec final → `GLHOST_SOCKET_ERROR connect port=<p> error=<wsa>`, ieșire 2.
3. Setează `TCP_NODELAY` (eșec → `GLHOST_SOCKET_ERROR TCP_NODELAY=<wsa>`, ieșire 2).
4. Pornește un fir care citește stdin-ul (citire brută Win32) și aruncă datele. La EOF sau
   eroare (dacă nu e deja în închidere): marchează „control EOF” și închide socketul (ca să
   deblocheze un `recv` în curs). Eșec la crearea firului →
   `GLHOST_SOCKET_ERROR control thread=<err>`, ieșire 2.
5. Scrie `GLHOST_NATIVE_SOCKET_CONNECTED port=<p>` și golește stderr. `native_socket_bridge.py`
   așteaptă acest marcaj (max. 10 s), altfel oprește totul.
6. Citire pe socket: `recv` întoarce 0 la EOF; erorile WSA se mapează la EINTR / EAGAIN /
   ECONNRESET / EIO; EINTR se reîncearcă. Scriere: buclă până la trimiterea completă.
7. La terminare: marchează închiderea, închide socketul, anulează I/O-ul sincron al firului
   de control și îl așteaptă max. 2 s, curăță Winsock și scrie (în ordine):
   `GLHOST_NATIVE_SOCKET_COUNTS rx=<octeți primiți pe socket> tx=<octeți trimiși pe socket>`
   și `GLHOST_NATIVE_SOCKET_STOP control_eof=<0|1> control_joined=<0|1>`, apoi golește stderr.
   Testul de paritate cere `control_eof=1 control_joined=1` după închiderea stdin-ului.

„Anulat” (folosit de DMA) = control EOF sau închidere în curs.

### 5.3 Atașarea DMA (la op 144)

Op 144 sosește pe socket ca prima înregistrare (lungime exact 28). Atașarea:

1. Citește fișierul `GLHOST_DMA_CONFIG`; dacă lipsește sau nu are 4 câmpuri, reîncearcă la
   5 ms, max. 5 s (oprindu-se la anulare). Format (o linie, separat prin spații):
   `<pid QEMU, zecimal> <adresa host a pc.ram, hex> <mărimea pc.ram, hex> <creation time, hex>`
   (hex fără prefix; creation time = FILETIME-ul procesului pe 64 de biți, unități de
   100 ns). Fișierul e scris atomic de `run_hmi.py` (fișier `.tmp` + rename) **după** ce
   renderer-ul s-a conectat, cu valori obținute prin QMP `info ramblock` și
   `GetProcessTimes`.
2. Validează payload-ul 144: versiune = 2; lungime = 135168; mărimea RAM = `0x20000000`;
   adresa fizică ≥ `0x100000`, aliniată la 4096, iar regiunea [fizic, fizic + lungime) în
   RAM; baza ≠ 0 și fără depășire aritmetică.
3. Deschide procesul cu drepturi VM_READ | VM_WRITE | VM_OPERATION |
   QUERY_LIMITED_INFORMATION; creation time trebuie să fie egal cu cel din config; numele
   imaginii (ultima componentă a căii) trebuie să fie, fără diferență de majuscule,
   `qemu-system-x86_64.exe`.
4. Adresa regiunii = bază + fizic. `VirtualQueryEx` pe ea: zona trebuie să fie
   MEM_COMMIT, protecție exact PAGE_READWRITE, iar toți cei 135168 de octeți în aceeași zonă.
5. Citește primii 44 de octeți: magic `NBT_DMA_RING_V2\0`; versiunea (16) = cea din
   payload; mărimea (20) = cea din payload; capacitatea (24) = 65536; nonce (28..43) = cei 16
   octeți din payload.
6. Cuvântul de la 64 = 0 (citire simplă) și contoarele de la 128, 192, 256, 320 valide și
   egale cu 0.
7. Scrie 1 la offset 64. Scrie
   `GLHOST_DMA_ATTACHED pid=<pid> physical=<hex> bytes=<lungime> bounded_adapter_region=1`.
8. Răspunde pe **socket** cu u32 = 1 și activează DMA-ul (de acum citirile „stdin” și
   scrierile „stdout” ale renderer-ului merg prin inele).

Orice eșec: se eliberează resursele, se răspunde pe socket cu u32 = 0 și sesiunea se
încheie **fără** linia „client disconnected” (ieșire 0). Dacă scrierea ack-ului eșuează,
la fel.

Scrierea în memoria QEMU: implementarea actuală folosește `NtWriteVirtualMemory` din
`ntdll.dll` (mai rapid decât `WriteProcessMemory`, măsurat); citirea folosește
`ReadProcessMemory`. Orice mecanism echivalent e acceptabil, cu condiția restricțiilor din
§5.4. Protecția paginilor nu se modifică niciodată.

### 5.4 Restricții de acces și operațiile pe inele (comportamentul „fast”)

**Restricții** (obligatorii, verificate de testul de contract):

- Orice acces trebuie să fie în [0, 135168); altfel e refuzat (EINVAL).
- Scrierile sunt permise **numai** ca: un cuvânt de 4 octeți la offseturile 64, 68, 192,
  196, 256, 260; sau orice interval complet inclus în [69632, 135168). Orice altă scriere
  (inclusiv 8 octeți la 192, sau 4 octeți la 0, 16, 20, 24, 28, 128, 320, 512, 4096, 69631,
  135168) e refuzată (EPERM) fără a atinge memoria.
- Eșecul unei operații de memorie scrie
  `GLHOST_DMA_MEMORY_ERROR write=<0|1> offset=<o> count=<n> done=<d> winerror=<e>` (EIO).

**Citire comenzi (TX), cu citire în bloc — obligatoriu:**

- Renderer-ul ține o copie locală (max. 65536 de octeți) a octeților deja consumați din
  inel. O cerere de N octeți se servește întâi din copia locală.
- Când copia e goală: dacă e anulat, întoarce ce s-a livrat până atunci (posibil 0 = EOF);
  citește TX head (128). Citire invalidă → așteptare (§5.12) și reîncercare; eroare de
  memorie → întoarce livrat sau −1. disponibil = head − tail: > 65536 →
  `GLHOST_DMA_BAD_TX head=<h> tail=<t>`, eroare (EPROTO); 0 → dacă s-a livrat ceva, întoarce
  parțial, altfel așteaptă. Altfel copiază **tot ce e disponibil până la capătul inelului**
  cu o singură citire cross-process în copia locală, publică tail-ul (192/196) o singură dată
  pentru tot blocul și continuă servirea din copie.
- Rezultatul este semantic identic cu citirea directă (aceleași octeți, aceeași ordine,
  livrări parțiale permise), dar înlocuiește citirile/publicările per înregistrare cu câte o
  singură citire și o singură publicare per bloc disponibil.

**Scriere răspunsuri (RX):** cât timp mai sunt octeți: dacă e anulat → EPIPE (întoarce
parțial sau −1); citește RX tail (320); invalid → așteaptă; used = RX head local − tail:
> 65536 → `GLHOST_DMA_BAD_RX head=<h> tail=<t>`, EPROTO; plin → așteaptă; altfel copiază
min(liber, până la capăt, rămas) la 69632 + poziție, avansează și publică RX head (256/260).

Contoarele de trafic DMA (octeți citiți / scriși prin inele) se raportează la final (§5.13).
Orice activitate (bloc citit sau scris) actualizează momentul „ultimei activități”.

### 5.5 Configurarea EGL/ANGLE (fereastra inițială)

Fereastra se creează o singură dată, la prima nevoie, cu (w, h) = argumentele op 1 dacă
sosește întâi un op 1, altfel 0, 0; valorile ≤ 0 sau > 8192 se înlocuiesc cu 800 respectiv
480.

1. `eglGetDisplay(EGL_DEFAULT_DISPLAY)`, `eglInitialize`.
2. `eglChooseConfig` cu: SURFACE_TYPE = PBUFFER_BIT, RENDERABLE_TYPE = OPENGL_ES2_BIT,
   RED/GREEN/BLUE/ALPHA = 8, DEPTH = 24, STENCIL = 8; se folosește prima configurație.
   Eșec sau 0 configurații → `EGL initialization failed <hex eglGetError>`, ieșire 1.
3. Pbuffer w × h; context cu CONTEXT_CLIENT_VERSION = 2, fără partajare; `eglMakeCurrent`.
   Eșec → `EGL context failed <hex>`, ieșire 1.
4. Scrie `glhost: window <w>x<h>, GLES = <GL_VERSION> | <GL_RENDERER>`.
5. Pe acest context inițial: viewport (0, 0, w, h), clear color (0.05, 0.05, 0.10, 1.0),
   clear color buffer, **publicare cadru** (§5.11) și `eglSwapBuffers`.

Dimensiunea ferestrei (w, h) e globală și fixă pe durata procesului; toate pbuffer-ele
clienților au aceeași dimensiune.

### 5.6 Clienți (procese guest) și spațiile de nume

- Op 119 setează „PID-ul cerut” (persistă până la următorul 119).
- Înainte de a executa orice înregistrare, **cu excepția** 144, 119, 122, 126, 127 și
  134–137, renderer-ul selectează clientul pentru PID-ul cerut:
  - dacă PID-ul cerut = PID-ul curent → nimic (inițial PID-ul curent e 0, deci PID 0
    folosește contextul inițial și tabelele implicite);
  - altfel se asigură că fereastra există (cu 0, 0 dacă nu exista), apoi caută clientul;
    unul nou primește: context GLES 2 propriu (fără partajare, aceeași configurație), pbuffer
    propriu win_w × win_h, tabelă proprie de nume (2²⁰ intrări, toate 0), metadate proprii
    de blend/atribute client. Maxim 32 de clienți (al 33-lea → `Too many graphics clients`,
    ieșire 1). Eșecuri de creare/alocare → ieșire 1 (fără mesaj).
  - `eglMakeCurrent` pe pbuffer-ul și contextul clientului (eșec → ieșire 1).
- Op 1 se tratează și **înaintea** selecției (astfel prima înregistrare op 1 fixează
  dimensiunea ferestrei).
- **Tabela de nume**: nume guest (u32 < 2²⁰) → obiect GL real; nume ≥ 2²⁰ se traduc la 0.
  Operațiile „gen” (15, 50, 78, 79) creează câte un obiect real per nume și îl memorează;
  7 și 10 creează shader/program și îl memorează; 130 șterge și pune 0.

### 5.7 Bucla de înregistrări și validarea

Pentru fiecare înregistrare: citește exact 8 octeți (opcode, lungime); EOF/eroare → sfârșit.
Lungime > 64 MiB → sfârșit. Citește exact payload-ul. Scrie în captură (dacă e activă).
Dacă opcode = 128 și lungimea = 12, opcode-ul devine 138 (format vechi). Validează; o
înregistrare invalidă scrie `Invalid graphics record: op=<op> len=<len>` și încheie
sesiunea (normal, ieșire 0). Apoi op 1 (fereastra), selecția clientului, execuția.

**Lungimi fixe** (payload exact): 1:8, 2:16, 3:16, 4:4, 5:0, 6:0, 7:8, 9:4, 10:4, 11:8,
12:4, 13:4, 16:8, 19:24, 20:4, 21:4, 29:8, 30:8, 31:12, 32:16, 33:4, 34:4, 35:8, 36:4,
37:4, 38:4, 39:4, 40:4, 42:4, 43:8, 51:8, 53:12, 54:4, 55:8, 57:4, 58:12, 60:8, 61:8,
62:20, 63:16, 64:16, 65:16, 66:16, 67:4, 68:4, 69:12, 70:12, 71:16, 72:4, 73:8, 75:8,
76:16, 77:16, 84:20, 85:8, 86:16, 87:8, 102:8, 103:8, 104:4, 105:0, 106:4, 107:4, 108:8,
109:4, 119:4. În plus: la 7, 10, 12, 13 primul câmp < 2²⁰; la 11 ambele câmpuri < 2²⁰.

**Reguli variabile** (cnt = câmpul indicat, toate produsele calculate pe 64 de biți):

| Op | Regulă |
| --- | --- |
| 8, 100, 101 | L ≥ 8, câmpul 0 < 2²⁰, câmpul@4 = L − 8 |
| 14 | L ≥ 12, câmpul@8 = L − 12 |
| 15, 50, 78, 79 | L ≥ 4, (L − 4) multiplu de 4, câmpul 0 = (L − 4)/4, fiecare id < 2²⁰ |
| 17 | L ≥ 12 și (L = 12 sau câmpul@4 = L − 12) |
| 18 | L ≥ 12, câmpul@8 = L − 12 |
| 22–25 | L ≥ 8, cnt@4 · k · 4 = L − 8 (k = op − 21) |
| 26–28 | L ≥ 12, cnt@4 · k² · 4 = L − 12 (k = op − 24) |
| 80–83 | L ≥ 8, cnt@4 · k · 4 = L − 8 (k = op − 79) |
| 52, 56 | L ≥ 36, câmpul@32 = L − 36 |
| 110 | L ≥ 12, cnt@0 · 4 + câmpul@8 = L − 12, fiecare id de shader < 2²⁰ |
| 120 | L = 24, w@8 și h@12 (i32) în 1..2048, câmpul@16 = `0x1908`, câmpul@20 = `0x1401` |
| 122, 126 | L = 4 |
| 123, 124 | L = 12, câmpul@8 ≤ 4096 |
| 125 | L = 4 și valoarea = 1 |
| 127 | L ≥ 24; w@4, h@8 în 1..2048 și pare; @12 în 1..60; @16 în 64000..20000000; @20 ≤ 1; w·h·4 = L − 24 |
| 128 | L ≥ 24, index@0 < 16, câmpul@20 = L − 24 |
| 129 | L ≥ 16, câmpul@12 = L − 16, count@4 · lățime(type@8) = L − 16 (lățime: `0x1401`→1, `0x1403`→2, altfel 4) |
| 130 | L ≥ 8, tip@0 ≤ 3, cnt@4 · 4 = L − 8 |
| 131 | L = 28, w@8, h@12 (i32) în 1..2048, @16 = `0x1908`, @20 = `0x1401` |
| 132 | L = 12, w@4, h@8 în 1..2048 |
| 133 | L = 4 |
| 134 | (L = 12 sau (L = 16 și @12 ≤ 1)), @4 și @8 în 1..2048 |
| 135 | 8 < L ≤ 16 MiB + 8, câmpul@4 = L − 8 |
| 136 | L = 68 |
| 137 | L = 4 |
| 138 | L = 12, count@0 ≤ 16 MiB, type@4 ∈ {`0x1401`, `0x1403`, `0x1405`} |
| 139 | L ≥ 28, i32@24 ≥ 0, (L = 28 sau 28 + câmpul@24 = L) |
| 140 | L = 32 |
| 141 | L = 8 |
| 142 | L = 4 |
| 143 | L = 8 |
| 144 | L = 28 |

Orice alt opcode (de ex. 0, 41, 44–49, 59, 74, 88–99, 111–118, 121, ≥ 145) este invalid.

### 5.8 Semantica fiecărui opcode pe host

Toate apelurile se fac pe contextul clientului curent. `N(x)` = obiectul real pentru numele
guest x. Payload-urile sunt cele din §2.6.

| Op | Execuție | Răspuns |
| --- | --- | --- |
| 1 | creează fereastra dacă nu există (§5.5); altfel nimic | — |
| 2 | glViewport | — |
| 3 | glClearColor | — |
| 4 | glClear | — |
| 5 | **swap**: dacă nu s-a desemnat un client primar sau clientul curent e cel primar → publicare cadru (`MHI2_GL_FRAME`); dacă `MHI2_GL_DUMP_CLIENTS` → publicare în `nbt-client-<pid>.ppm`; `eglSwapBuffers` pe pbuffer-ul curent; contor global de cadre +1; dacă numărul de ordine (1-based) e 1, 2, 3 sau 1 + multiplu de 120 → `glhost: <n> frames swapped` | — |
| 6 | glFinish | — |
| 7 | creează shader de tipul dat, memorează sub id; resetează modul de blend al shaderului la 0 | — |
| 8 | scrie textul în fișierul `nbt-source-<id>.glsl` (director curent, diagnostic); resetează modul de blend al shaderului; glShaderSource(N(id), 1, text, lungime explicită) | — |
| 9 | glCompileShader(N(id)) + verificare (§5.9) cu eticheta `compile` | — |
| 10 | resetează metadatele programului (mod 0, fragment 0); creează program, memorează | — |
| 11 | interoghează GL_SHADER_TYPE al N(shader); dacă e FRAGMENT (`0x8B30`), memorează că fragmentul programului este acest nume guest; glAttachShader | — |
| 12 | glLinkProgram + verificare cu eticheta `link`; modul de blend al programului := modul shaderului fragment memorat (în acest moment) | — |
| 13 | glUseProgram(N(p)); interoghează GL_CURRENT_PROGRAM; dacă e egal cu N(p), programul activ (pentru blend) := p | — |
| 14 | glBindAttribLocation cu numele trunchiat la 255 de caractere | — |
| 15 | creează câte un buffer per nume | — |
| 16 | glBindBuffer(target, N(id)) | — |
| 17 | glBufferData; date = payload + 12 dacă size > 0 și payload-ul le conține, altfel NULL | — |
| 18 | glBufferSubData; idem | — |
| 19 | dacă GL_ARRAY_BUFFER_BINDING = 0 → `glhost: vertex array lacks transferred buffer`, sesiunea se încheie (fără linia „client disconnected”); altfel glVertexAttribPointer cu normalized ≠ 0 → TRUE și pointer = offsetul | — |
| 20 / 21 | glEnable/DisableVertexAttribArray | — |
| 22–28 | glUniform*fv / glUniformMatrix*fv (transpose ≠ 0 → TRUE) | — |
| 29 | glUniform1f | — |
| 30 | glUniform1i | — |
| 31 | desenare cu blend override (§5.10.3): glDrawArrays | — |
| 32 | desenare cu override: glDrawElements cu offsetul ca pointer în EBO | — |
| 33–39 | glEnable, glDisable, glBlendFunc, glDepthFunc, glCullFace, glFrontFace, glDepthMask (≠0 → TRUE) | — |
| 40, 42, 43 | glClearDepthf, glLineWidth, glPolygonOffset | — |
| 50 | creează câte o textură per nume | — |
| 51 | glBindTexture(target, N(id)) | — |
| 52 / 56 | glTexImage2D / glTexSubImage2D; date = payload + 36 dacă S > 0 și prezente, altfel NULL | — |
| 53, 54, 55, 57, 58 | glTexParameteri, glActiveTexture, glPixelStorei, glGenerateMipmap, glTexParameterf | — |
| 60, 61 | glBindFramebuffer / glBindRenderbuffer cu N(id) | — |
| 62 | glFramebufferTexture2D cu N(textură) | — |
| 63 | glRenderbufferStorage | — |
| 64 | glFramebufferRenderbuffer cu N(rb) | — |
| 65–73, 75–77 | funcțiile GL corespunzătoare (§2.6), argumente directe | — |
| 78, 79 | creează framebuffere / renderbuffere per nume | — |
| 80–83 | glUniform{1..4}iv | — |
| 84 | glVertexAttrib4fv(index, cele 4 valori) | — |
| 85, 86, 87 | glDepthRangef, glBlendColor, glHint | — |
| 100 / 101 | glGetAttribLocation / glGetUniformLocation pe N(p), nume trunchiat la 255 | 4 (i32). Dacă scrierea eșuează: `glhost: getter reply failed`, se continuă |
| 102 / 103 | glGetShaderiv / glGetProgramiv pe N(x), inițial 0 | 4 |
| 104 | dacă pname ∈ {`0x86A2`, `0x86A3`, `0x8DF8`, `0x8DF9`} (NUM_/COMPRESSED_TEXTURE_FORMATS, SHADER_BINARY_FORMATS, NUM_SHADER_BINARY_FORMATS) → nu se apelează GL; altfel glGetIntegerv într-un tablou de 16 inițializat cu 0 | 64 |
| 105 | glGetError | 4 |
| 106 | ca 104, glGetBooleanv, 16 × 1 octet | 16 |
| 107 | ca 104, glGetFloatv, 16 × f32 | 64 |
| 108 | glGetShaderPrecisionFormat(shadertype, precisiontype, range, &precision), inițial 0 | 12 (range0, range1, precision) |
| 109 | glCheckFramebufferStatus | 4 |
| 110 | §5.10 | — |
| 119 | PID-ul cerut := valoarea | — |
| 120 | citire pixeli (§5.9) din framebuffer-ul curent al clientului | w·h·4 |
| 122, 126, 127, 134–137 | `Unsupported video/encoder record <op>`, ieșire 3 | — |
| 123 / 124 | glGetActiveAttrib / glGetActiveUniform(N(p), index, bufSize = c, …) într-un buffer de 4096 inițializat cu 0 | 12 (length, size, type) + exact c octeți din buffer |
| 125 | clientul primar := clientul curent | — |
| 128 | §5.10.4 | — |
| 129 | desenare cu override: salvează GL_ELEMENT_ARRAY_BUFFER_BINDING, leagă 0, glDrawElements cu indicii din payload (offset 16), restaurează legătura | — |
| 130 | pentru fiecare id: id = 0, ≥ 2²⁰ sau nemapat → ignorat; altfel șterge obiectul (tip 0 textură, 1 buffer, 2 framebuffer, 3 renderbuffer) și pune 0 în tabelă | — |
| 131 | ca 120, dar după trimiterea pixelilor îi păstrează în cache-ul de cadre native cu id = câmpul@24 (§5.10.5) | w·h·4 |
| 132 | dacă cache-ul are id-ul cu exact w × h: încarcă pixelii în textura legată la GL_TEXTURE_2D (§5.9) și răspunde 1; altfel 0 | 4 |
| 133 | elimină din cache intrările cu id-ul dat **ale clientului curent** | — |
| 138 | index maxim din EBO (§5.9) | 4 (u32; `0xFFFFFFFF` = imposibil) |
| 139 | glCompressedTexImage2D(target, level, fmt, w, h, border, imageSize = i32@24, date = payload + 28 dacă L > 28, altfel NULL) | — |
| 140 | glCopyTexSubImage2D | — |
| 141 | glGetVertexAttribiv într-un tablou de 4 inițializat cu 0 | 16 |
| 142 | glIsEnabled → 1/0 | 4 |
| 143 | glSampleCoverage(value, invert ≠ 0 → TRUE) | — |
| 144 | atașare DMA (§5.3) | 4 pe **socket** |

Dacă scrierea unui răspuns (oricare în afară de 100/101) eșuează, sesiunea se încheie fără
linia „client disconnected”.

### 5.9 Apelurile GL „ascunse” (obligatorii pentru paritatea `glGetError`)

Răspunsurile `glGetError` (95 % din traficul sincron) depind de **toate** apelurile GL făcute
pe contextul clientului, inclusiv cele pe care renderer-ul le face din proprie inițiativă.
Pentru răspunsuri identice octet cu octet, implementarea nouă trebuie să facă exact aceste
apeluri suplimentare, în aceeași ordine, și **niciun alt apel GL** care ar putea genera erori:

| Context | Apeluri suplimentare |
| --- | --- |
| op 9 | după compilare: glGetShaderiv(COMPILE_STATUS); dacă e 0, glGetShaderInfoLog (buffer 1024) |
| op 12 | după link: glGetProgramiv(LINK_STATUS); dacă e 0, glGetProgramInfoLog (1024) |
| op 110 cu shader găsit | glShaderSource(N(s), 1, text, NULL), glCompileShader, apoi ca la op 9 |
| op 11 | glGetShaderiv(N(shader), GL_SHADER_TYPE) **înainte** de glAttachShader (dacă numele e invalid generează eroarea GL normală) |
| op 13 | glGetIntegerv(GL_CURRENT_PROGRAM) după glUseProgram |
| op 19 | glGetIntegerv(GL_ARRAY_BUFFER_BINDING) înainte |
| op 128 | glGetIntegerv(GL_ARRAY_BUFFER_BINDING); glBindBuffer(ARRAY, 0); glVertexAttribPointer(index, size, type, norm brut, stride, copia locală); glBindBuffer(ARRAY, legătura salvată) |
| op 129 | glGetIntegerv(GL_ELEMENT_ARRAY_BUFFER_BINDING); glBindBuffer(ELEMENT, 0); draw; glBindBuffer(ELEMENT, salvat) |
| op 31/32/129 cu mod de blend ≠ 0 | înainte: glIsEnabled(BLEND); glGetIntegerv pentru BLEND_SRC_RGB, BLEND_DST_RGB, BLEND_SRC_ALPHA, BLEND_DST_ALPHA, BLEND_EQUATION_RGB, BLEND_EQUATION_ALPHA (în această ordine); glEnable(BLEND); glBlendEquationSeparate(FUNC_ADD, FUNC_ADD); glBlendFuncSeparate(modul). După draw: glBlendFuncSeparate(salvate); glBlendEquationSeparate(salvate); glDisable(BLEND) dacă inițial era dezactivat |
| op 120/131 | glGetIntegerv(GL_PACK_ALIGNMENT); glPixelStorei(PACK, 1); glReadPixels(x, y, w, h, RGBA, UNSIGNED_BYTE); glPixelStorei(PACK, valoarea salvată) |
| op 132 (hit) | glGetIntegerv(GL_UNPACK_ALIGNMENT); glPixelStorei(UNPACK, 1); glTexImage2D(TEXTURE_2D, 0, RGBA, w, h, 0, RGBA, UNSIGNED_BYTE, pixeli); glPixelStorei(UNPACK, salvat) |
| op 138 | glGetBufferParameteriv(ELEMENT_ARRAY_BUFFER, BUFFER_SIZE) **întotdeauna** (fără EBO legat generează INVALID_OPERATION, care va fi raportat de un glGetError ulterior); apoi, numai dacă type e valid, count > 0, funcțiile `glMapBufferRange` și `glUnmapBuffer` sunt obținute prin `eglGetProcAddress` și offset + count·lățime ≤ BUFFER_SIZE: glMapBufferRange(ELEMENT, offset, count·lățime, MAP_READ_BIT = 1); dacă maparea reușește, maximul indicilor (little-endian, lățimea tipului), apoi glUnmapBuffer. Altfel răspuns `0xFFFFFFFF` |
| op 5 (publicare) | glReadPixels(0, 0, win_w, win_h, RGBA, UNSIGNED_BYTE) **fără** a schimba PACK_ALIGNMENT, din framebuffer-ul legat curent al clientului (de regulă pbuffer-ul) |
| op 104/106/107 cu pname exclus | niciun apel GL |

Pentru op 138 contextul trebuie să ofere `glMapBufferRange`/`glUnmapBuffer` prin
`eglGetProcAddress` (ANGLE le oferă și pe un context cerut ca ES 2); testul de paritate
cere rezultatul 7 pentru indicii `[2, 7, 1]`.

### 5.10 Shadere și moduri de blend

#### 5.10.1 Shadere binare NVIDIA (op 110)

Firmware-ul încarcă shadere precompilate NVIDIA (format `0x890B`), pe care ANGLE nu le
poate folosi; ele se înlocuiesc cu GLSL extras anterior din resursele firmware-ului.

1. Scrie octeții binarului în `nbt-shader-<k>-<format în hex minuscul>.bin` în directorul
   curent (k = contor global care începe de la 0 și crește la fiecare op 110; diagnostic) și
   scrie pe stderr `shader binary <cale> count=<count> size=<length>`.
2. hash = FNV-1a pe 64 de biți peste octeții binarului (offset basis 14695981039346656037,
   prime 1099511628211).
3. Numai dacă count = 1 și `MHI2_SHADER_CACHE` e setat: citește
   `<dir>/<hash ca 16 cifre hex minuscule>-<length zecimal>.blend` (text: un întreg zecimal,
   trebuie ≤ 5) și `<dir>/<același>.glsl` (1 octet .. 1 MiB, citit integral). Ambele
   valide → modul de blend al shaderului (numele guest din listă) := valoarea din `.blend`;
   se compilează GLSL-ul în N(shader) (§5.9) cu eticheta `firmware source shader`.
4. Altfel: `UNSUPPORTED NVIDIA shader hash=<hash, 16 cifre hex minuscule>`, ieșire 4.

Directorul `work/graphics-port/host/shader-cache` conține 214 perechi `.blend`/`.glsl`;
fișierele nu se modifică.

#### 5.10.2 Verificarea compilării/link-ului

Dacă statusul e 0: `glhost: <etichetă> FAILED: <log>` (log-ul GL trunchiat la 1023 de
caractere). Etichete: `compile`, `link`, `firmware source shader`.

#### 5.10.3 Override-ul de blend

Programele NVIDIA încorporează operația „source-over” în fragment; versiunea GLSL emite
culoare premultiplicată și cere un blend fix doar pe durata draw-ului. Modul de blend:
per shader (din `.blend`, resetat la 0 de op 7 și op 8), per program (calculat la link din
fragmentul atașat), iar draw-ul folosește modul programului activ (op 13). Mod 0 = nicio
intervenție. Pentru modurile 1–5, ecuația e FUNC_ADD pentru RGB și alfa, iar
glBlendFuncSeparate(srcRGB, dstRGB, srcA, dstA) este:

| Mod | srcRGB | dstRGB | srcAlpha | dstAlpha |
| --- | --- | --- | --- | --- |
| 1 | ONE | ONE_MINUS_SRC_ALPHA | ONE | ONE_MINUS_SRC_ALPHA |
| 2 | ONE | ONE_MINUS_SRC_ALPHA | ZERO | ONE |
| 3 | SRC_ALPHA | ONE_MINUS_SRC_ALPHA | SRC_ALPHA | ONE_MINUS_SRC_ALPHA |
| 4 | ONE | ZERO | ONE | ZERO |
| 5 | ZERO | ZERO | ZERO | ZERO |

Starea de blend a guest-ului este restaurată după fiecare draw (§5.9). Metadatele (moduri
per shader/program, fragmentul atașat, programul activ) sunt **per client**.

#### 5.10.4 Atribute client (op 128)

Per client și per index (0–15) se păstrează o copie a octeților primiți (realocată la
fiecare op 128; alocare eșuată → ieșire 1); pointerul atributului GL indică această copie
(cu ARRAY_BUFFER dezlegat temporar, §5.9). Copia rămâne valabilă până la următorul op 128 pe
același index.

#### 5.10.5 Cache-ul de cadre native (op 131–133)

16 intrări globale {id, w, h, client proprietar, moment ultimei utilizări, pixeli RGBA}.
Stocare (op 131): dacă id-ul există deja, intrarea lui se înlocuiește; altfel se folosește o
intrare liberă sau, dacă nu există, cea folosită cel mai demult. Proprietarul e clientul
curent. Op 132 cu potrivire actualizează momentul utilizării.

### 5.11 Publicarea cadrelor (comportamentul „fast”, obligatoriu)

**Formatul PPM**: antet ASCII `P6\n<w> <h>\n255\n`, urmat de w·h·3 octeți RGB; primul rând
din fișier este rândul de **sus** al imaginii, adică ultimul rând întors de glReadPixels
(rândurile se inversează); canalul alfa se elimină. Pentru 1280×480 fișierul are exact
1843216 octeți.

**Înlocuire atomică**: se scrie `<cale>.tmp` complet (eșec la scriere/închidere → cadrul nu
se publică, fără mesaj), apoi se mută peste `<cale>` cu înlocuire și write-through
(`MoveFileEx` cu `MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH`). Consumatorii nu văd
niciodată un fișier parțial.

**Când se publică**: la crearea ferestrei (cadrul inițial, culoare de fundal) și la fiecare
op 5 conform §5.8. Fără deduplicare, fără limitare de rată, **fără cadre sărite**.

**Publicare în afara firului GL** (cerință „fast”):

- `glReadPixels` rămâne pe firul GL, la momentul swap-ului, deci pixelii sunt exact cei ai
  acelui swap.
- Conversia RGBA→RGB, scrierea fișierului și înlocuirea atomică se fac pe **un singur** fir
  lucrător.
- Există cel mult **un** cadru în așteptare: după readback, firul GL așteaptă terminarea
  publicării anterioare (dacă e în curs), copiază pixelii în bufferul lucrătorului și îl
  semnalează. Astfel fiecare cadru e publicat, în ordine.
- Dacă dimensiunea se schimbă, se așteaptă întâi lucrătorul.
- Dacă firul nu poate fi creat, calea depășește 4095 de caractere sau alocarea eșuează,
  publicarea se face sincron (același rezultat).
- La terminare, renderer-ul așteaptă publicarea ultimului cadru și oprește lucrătorul
  **înainte** de închiderea DMA și a socketului.
- Liniile de log (`frames swapped`) pot apărea înainte ca fișierul cadrului respectiv să fie
  înlocuit; consumatorii tolerează asta.

### 5.12 Politica de așteptare (idle)

Când inelul nu are date/spațiu sau contorul e invalid: dacă de la ultima activitate au
trecut < 3 ms, se cedează procesorul activ (spin cu `YieldProcessor`); altfel se așteaptă
~1 ms cu un **timer de rezoluție înaltă** (`CreateWaitableTimerExW` cu
`CREATE_WAITABLE_TIMER_HIGH_RESOLUTION`, termen relativ 1 ms), fără a schimba rezoluția
timerului sistemului; numai dacă timerul nu e disponibil se folosește `Sleep(1)`. (Motiv:
`Sleep(1)` durează un tick întreg, ~15,6 ms, ceea ce ar întârzia fiecare cadru.)

### 5.13 Terminare

Ordinea: sfârșitul buclei → (dacă sesiunea s-a încheiat prin `break`, nu prin eșec de
răspuns/atașare/op 19) `glhost: client disconnected after <n> frames` → oprirea
lucrătorului de publicare (cu așteptarea ultimului cadru) → dacă DMA a fost atașat: scrie 1
la offset 68 (stop pentru guest) și `GLHOST_DMA_COUNTS rx=<octeți citiți din inelul TX> tx=<octeți scriși în inelul RX>`
→ închiderea transportului socket (§5.2 pasul 7) → ieșire 0.

### 5.14 Liniile stderr și consumatorii lor

| Linie (exactă) | Consumator / rol |
| --- | --- |
| `GLHOST_NATIVE_SOCKET_CONNECTED port=<p>` | `native_socket_bridge.py`: condiție de pornire (subșirul `GLHOST_NATIVE_SOCKET_CONNECTED port=`) |
| `GLHOST_NATIVE_SOCKET_COUNTS rx=<n> tx=<n>` | `native_socket_bridge.py` (regex `GLHOST_NATIVE_SOCKET_COUNTS rx=(\d+) tx=(\d+)`) |
| `GLHOST_DMA_COUNTS rx=<n> tx=<n>` | `native_socket_bridge.py` (regex `GLHOST_DMA_COUNTS rx=(\d+) tx=(\d+)`) |
| `GLHOST_NATIVE_SOCKET_STOP control_eof=<0|1> control_joined=<0|1>` | `test_angle_parity.py` cere `control_eof=1 control_joined=1` |
| `glhost: <n> frames swapped` | `viewer.py` (regex `glhost:\s+[1-9]\d*\s+frames swapped`), `run_hmi.py` (`glhost: (\d+) frames swapped`), `session.py` și `run_input_diagnostic.py` (subșirul `frames swapped`, ca semn că HMI-ul randează) |
| `glhost: client disconnected after <n> frames` | `run_hmi.py` (număr final de prezentări) |
| `Invalid graphics record: op=<op> len=<len>` | `test_angle_parity.py` cere absența |
| `GLHOST_DMA_MEMORY_ERROR …`, `GLHOST_DMA_BAD_TX …`, `GLHOST_DMA_BAD_RX …` | `test_angle_parity.py` cere absența (prefixul `GLHOST_DMA_BAD_`) |
| `GLHOST_DMA_ATTACHED pid=<pid> physical=<hex> bytes=<n> bounded_adapter_region=1` | diagnostic |
| `glhost: window <w>x<h>, GLES = <ver> \| <renderer>` | diagnostic |
| `shader binary <cale> count=<c> size=<s>` | diagnostic |
| `UNSUPPORTED NVIDIA shader hash=<16 hex>` | diagnostic (unelte de audit caută șirul) |
| `glhost: <etichetă> FAILED: <log>` | diagnostic |
| `glhost: vertex array lacks transferred buffer`, `glhost: getter reply failed`, `glhost: OOM <len>`, `Too many graphics clients`, `Unsupported video/encoder record <op>`, `EGL initialization failed <hex>`, `EGL context failed <hex>`, `Invalid compressed texture record`, `Invalid texture copy record`, `Invalid vertex attribute query`, `Invalid capability query`, `Invalid sample coverage record`, `GLHOST_SOCKET_ERROR …` | diagnostic |
| `glhost op=<op> len=<len>` | doar cu `MHI2_GL_TRACE` |

---

## 6. Criterii de compatibilitate și acceptare (teste „black-box”)

### 6.1 `perf-shared/test_angle_parity.py` (obligatoriu, pentru ambele denumiri ale renderer-ului)

Pornește un QEMU gol (`-S`, WHPX, 512 MiB, fără firmware), află `pc.ram` prin QMP, scrie
direct în RAM-ul VM-ului o regiune DMA la fizic `0x100000` (header V2, nonce
`42, 73, 101, 0x100000`, contoare 0), scrie configul DMA, pornește renderer-ul cu
`GLHOST_DMA_CONFIG`, `GLHOST_QEMU_PORT`, `MHI2_GL_FRAME`, `MHI2_SHADER_CACHE` și cwd =
`work/graphics-port/host`, acceptă conexiunea și trimite op 144. Cere:

1. ack exact `01 00 00 00` pe socket;
2. după ce trimite în inelul TX captura reală
   `host/perf-publish/parity-1793192870752795000/original-plus-real-ebo-query.bin`
   (15 634 006 octeți, înregistrări cu prefix 119, inclusiv o interogare op 138 pe indicii
   `[2, 7, 1]`), toți cei **47 850** de octeți de răspuns citiți din inelul RX sunt identici
   cu `baseline_socket/reply.bin` (SHA256 răspuns `7976f735…e9`);
3. `frame.ppm` final identic octet cu octet cu `baseline_socket/frame.ppm` (1280×480,
   1 843 216 octeți, SHA256 `7ceedef1…045f`);
4. după închiderea stdin-ului: ieșire 0, `control_eof=1 control_joined=1` în log, fără
   `Invalid graphics record`, `GLHOST_DMA_MEMORY_ERROR`, `GLHOST_DMA_BAD_`;
5. indexul maxim EBO = 7 (verificat implicit prin octeții de răspuns).

`host/perf-batch/test_parity.py --stage fast` rulează același test cu calea
`nbt-glhost-dma-fast.exe`.

### 6.2 Contractul inelelor (echivalent pentru noua implementare)

`perf-shared/test_dma.c` este un test white-box legat de structura internă veche și nu se
aplică direct. Implementarea nouă trebuie să ofere un test propriu care verifică aceleași
proprietăți (rezultatul vechi: `DMA_CONTRACT_PASS bytes_each_direction=… cursor32_wrap=1 ring_wrap=1 partial_reads=1 bounds=1 native_kernel_calls=1 eof_joined=1`):
flux exact în ambele direcții (8 MiB + 73 sintetic și captura reală de 24,6 MB), trecerea
cursorului peste 2³² (start la `0xFFFFFFF0` pentru TX și `0xFFFFFFA1` pentru RX), mii de
wrap-uri de inel, citiri parțiale cu mărimi 1, 4, 8, 4095, 65535, 65536, 121, refuzul
scrierilor din §5.4, refuzul ocupării invalide (TX head = tail + 65537 → EPROTO; RX tail =
head − 65537 → EPROTO), un cititor blocat întoarce 0 la „control EOF”, iar octeții din afara
regiunii rămân neatinși.

### 6.3 Rulări complete (VM real)

- `run_hmi.py` / `viewer.py` / `RUN_NBT.cmd`: în `serial_com1.log` apar
  `VIRTIO_FLOW_CONTROLLED_PORT_READY id=1 …`, `… id=2 …`, `NBT_MTP_VIRTIO_BIDIRECTIONAL_READY…`,
  `NBT_DMA_TRANSPORT_READY …`, `VIRTIO_DRIVER_READY status=7 …`; în `relay/renderer-stderr.log`
  apar `GLHOST_NATIVE_SOCKET_CONNECTED`, `GLHOST_DMA_ATTACHED`, `glhost: 1 frames swapped`;
  `frame.ppm` e un P6 complet (regex `P6\s+(\d+)\s+(\d+)\s+255[ \t]*\r?\n`, mărime = antet +
  w·h·3); `viewer.py` afișează cadre cu conținut (cadrul inițial e filtrat: diferență
  max−min ≤ 24 pe eșantioane).
- `session.py` cu HAL de tastatură: confirmarea `0xFD` pentru cheia 0 cu ready = 1 apare
  după afișarea meniului; fiecare buton produce `NBT_KEYBOARD_EVENT_POSTED` și o confirmare
  `0xFD`; nu apar `NBT_KEYBOARD_PACKET_REJECTED` / `…NATIVE_QUEUE_NOT_READY` / `…NATIVE_POST_FAILED`
  (`test_buttons_runtime.py`).
- `record_result.py` cere `NBT_DMA_TRANSPORT_READY` în serial.
- Performanță (nu e criteriu de corectitudine, dar e cerința variantei „fast”): cadru activ
  ~12 ms pe PC-ul de dezvoltare (față de ~20 ms fără optimizări), măsurat cu
  `work/perf-analysis/run_split.py --renderer fast`.

---

## 7. Ce NU prescrie această specificație

Implementatorul decide liber:

- structura internă, limbajul (C recomandat pentru guest din cauza ABI-ului), numele
  funcțiilor/variabilelor/tipurilor, organizarea fișierelor și a build-ului (cu condițiile
  ABI din §2.1);
- structurile de date: cum se păstrează starea per fir, tabelele de nume, lista de clienți,
  cache-ul de cadre, cache-ul inelului, coada de publicare (cu condiția semanticii descrise);
- mecanismele de sincronizare (lacăt, evenimente, cozi), atât timp cât ordinea și
  atomicitatea înregistrărilor și regula „un cadru în așteptare, niciunul sărit” sunt
  respectate;
- strategia exactă de spin/pauză din guest, în limitele timeout-urilor date;
- comportamentul în situații de eșec care oricum opresc procesul sau sesiunea (de exemplu
  vechea implementare lasă lacătul ținut dacă un răspuns parțial pentru op 123/124 eșuează;
  noua implementare îl poate elibera);
- implementarea căii de date virtio pentru GL (nefolosită când DMA reușește) și a modului
  stdio al renderer-ului (recomandat, nu obligatoriu);
- fișierele de diagnostic `nbt-source-<id>.glsl` și `nbt-shader-<k>-<fmt>.bin` (recomandate
  pentru uneltele de audit din `host/`, nu verificate de teste).

Nu se schimbă: firmware-ul BMW, IFS-urile existente, `shader-cache`, ANGLE-ul, scripturile
consumatoare.

---

## Anexa A. Funcțiile GLES stub (82)

Fiecare scrie o singură dată `glbridge: unsupported <nume>\n` pe fd 2 și întoarce 0:

glBeginPerfMonitorAMD, glBindVertexArrayOES, glCompressedTexImage3DOES,
glCompressedTexSubImage2D, glCompressedTexSubImage3DOES, glCopyTexImage2D,
glCopyTexSubImage3DOES, glDeleteFencesNV, glDeletePerfMonitorsAMD, glDeleteVertexArraysOES,
glDisableDriverControlQCOM, glDiscardFramebufferEXT, glEGLImageTargetRenderbufferStorageOES,
glEnableDriverControlQCOM, glEndPerfMonitorAMD, glEndTilingQCOM, glExtGetBufferPointervQCOM,
glExtGetBuffersQCOM, glExtGetFramebuffersQCOM, glExtGetProgramBinarySourceQCOM,
glExtGetProgramsQCOM, glExtGetRenderbuffersQCOM, glExtGetShadersQCOM,
glExtGetTexLevelParameterivQCOM, glExtGetTexSubImageQCOM, glExtGetTexturesQCOM,
glExtIsProgramBinaryQCOM, glExtTexObjectStateOverrideiQCOM, glFinishFenceNV,
glFramebufferTexture3DOES, glGenFencesNV, glGenPerfMonitorsAMD, glGenVertexArraysOES,
glGetAttachedShaders, glGetBufferParameteriv, glGetBufferPointervOES,
glGetDriverControlStringQCOM, glGetDriverControlsQCOM, glGetFenceivNV,
glGetFramebufferAttachmentParameteriv, glGetPerfMonitorCounterDataAMD,
glGetPerfMonitorCounterInfoAMD, glGetPerfMonitorCounterStringAMD, glGetPerfMonitorCountersAMD,
glGetPerfMonitorGroupStringAMD, glGetPerfMonitorGroupsAMD, glGetProgramBinaryOES,
glGetRenderbufferParameteriv, glGetShaderSource, glGetTexParameterfv, glGetTexParameteriv,
glGetTexStreamDeviceAttributeivIMG, glGetTexStreamDeviceNameIMG, glGetUniformfv,
glGetUniformiv, glGetVertexAttribPointerv, glGetVertexAttribfv, glIsBuffer, glIsFenceNV,
glIsFramebuffer, glIsProgram, glIsRenderbuffer, glIsShader, glIsTexture, glIsVertexArrayOES,
glMapBufferOES, glMultiDrawArraysEXT, glMultiDrawElementsEXT, glProgramBinaryOES,
glReleaseShaderCompiler, glSelectPerfMonitorCountersAMD, glSetFenceNV, glStartTilingQCOM,
glTestFenceNV, glTexBindStreamIMG, glTexImage3DOES, glTexParameterfv, glTexParameteriv,
glTexSubImage3DOES, glUnmapBufferOES, glValidateProgram, glVertexAttribPointerBounds.

## Anexa B. Marcaje guest (serial) și consumatori

| Marcaj | Consumator |
| --- | --- |
| `VIRTIO_FLOW_CONTROLLED_PORT_READY id=1 rx_queue=4 tx_queue=5` / `id=2 rx_queue=6 tx_queue=7` | unelte de diagnostic / audit (`timeout-audit`) |
| `NBT_MTP_VIRTIO_BIDIRECTIONAL_READY_PORT2_50123 …` | `session.py` (subșir `NBT_MTP_VIRTIO_BIDIRECTIONAL_READY`) — condiție înainte de a trimite înregistrările de dispozitiv |
| `NBT_MTP_VIRTIO_TCP_NODELAY fd=… result=… errno=… value=…` | `timeout-audit/tcp-nodelay` |
| `NBT_DMA_TRANSPORT_READY physical=<hex> bytes=135168 capacity=65536 original_stream=1` | `record_result.py`, `measure_owned_memory.py` |
| `NBT_KEYBOARD_CAPABILITY ready=<0|1> …` | `observe_keyboard.py`, `observe_home.py` |
| `NBT_KEYBOARD_EVENT_POSTED number=<n> key=<k> pressed=<p> …` | `test_buttons_runtime.py` |
| `NBT_KEYBOARD_PACKET_REJECTED`, `NBT_KEYBOARD_NATIVE_QUEUE_NOT_READY`, `NBT_KEYBOARD_NATIVE_POST_FAILED` | `test_buttons_runtime.py` (trebuie să lipsească) |
| `NBT_VFAST_PERF_FRAME frame=<n> qnx_realtime_ns=<ns> …` | `benchmark_navigation.py` |
| `VIRTIO_WAIT_TIMEOUT …`, `glbridge: virtio init failed code=<n>` | `perf-guest/build_wait_variants.py` și analize de eroare |
| restul (`VIRTIO_PCI`, `VIRTIO_FEATURES`, `VIRTIO_QUEUE`, `VIRTIO_DMA_ALLOC`, `VIRTIO_CONTROL_*`, `VIRTIO_DRIVER_READY`, `NBT_DMA_HOST_STOPPED`, `NBT_DMA_WAIT_TIMEOUT`, `NBT_PORT2_*`, `NBT_KEYBOARD_*`, `NBT_MTP_VIRTIO_*`) | diagnostic; păstrați textul exact |
