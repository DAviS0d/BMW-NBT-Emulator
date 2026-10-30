# Raport: rescrierea clean-room a punții GLES (shim QNX + renderer Windows)

© 2026 davisod & JEtsKi

## Metoda

Rolurile sunt separate. Separarea e organizată și documentată, nu verificată tehnic.

| Rol | Cine | Ce a văzut |
|---|---|---|
| Specificație („dirty room”) | agent separat | codul vechi (`perf-guest/dma`, `host/perf-dma`, `perf-batch` fast) și consumatorii lui |
| Implementare („clean room”) | **alt** agent, nou, fără acces la conversația principală | **doar** `docs/SPEC_GLES_BRIDGE.md`, headerele Khronos/ANGLE și toolchain-ul; i s-a interzis explicit să deschidă sursele vechi |
| Verificare | conversația principală | ambele variante (testele de paritate și comparația de similaritate) |

Conversația principală a citit în trecut fragmente din codul vechi, de aceea nu scrie cod nou.
Comunicarea cu implementatorul se face doar prin specificație și prin rezultate de test
descrise comportamental (ce răspuns sau pixel diferă), niciodată prin fragmente de cod vechi.

## Etapa 1 — specificația

`docs/SPEC_GLES_BRIDGE.md`, 1.392 de linii. Acoperă:

- biblioteca guest: ABI, exporturi, opcode-uri și layout-uri, regulile de batch și lacăt,
  inițializarea, intrarea MTP și HAL-ul de tastatură;
- transportul virtio și DMA;
- renderer-ul Windows: contractul procesului, atașarea DMA, dispatch-ul GL, shaderele,
  publicarea cadrelor, varianta „fast”;
- marcajele de log și consumatorii lor;
- criteriile de acceptare.

Verificarea automată a specificației: nu are blocuri de cod (singurul bloc delimitat e o
diagramă ASCII), nu are definiții `struct`/`#define`/`static` și nu are corpuri de funcții.
Liniile semnalate de scanare sunt proză, notație API Khronos sau tabele de layout.

Faptele marcate de autorul specificației ca nesigure sunt deduse, neverificate la rulare:
- backend-ul ANGLE implicit (D3D11);
- `_fini` → `DT_FINI` la link-are;
- `memcpy`/`memset` furnizate static de compiler-rt;
- momentul `PORT_OPEN` pentru `nbtinput`;
- repeat implicit 1 pentru butoane;
- pachetele 0xFC (DOOM);
- consumatorii din `timeout-audit`;
- `test_dma.c`, care depinde de structura internă veche și e înlocuit cu un test echivalent.

## Unealta de similaritate și calibrarea ei

`work/cleanroom-audit/similarity.py` funcționează ca MOSS:
- tokenizare C fără comentarii, în două vederi: „brut” (identificatori păstrați) și
  „structural” (identificatori și literale normalizate);
- k-grame de 12 tokeni, winnowing cu fereastra 8;
- procentul de amprente ale codului nou regăsite în cel vechi, cea mai lungă secvență comună
  de tokeni și liniile identice netriviale.

| Calibrare | Amprente comune (brut) | Structural | Cea mai lungă secvență comună |
|---|---:|---:|---:|
| Pozitiv: shim-ul vechi față de qemu-mhi2 `upstream/` (derivat cunoscut) | 62,9% | 50,8% | 6.093 de tokeni |
| Negativ: cod C al nostru fără legătură (`wal-lifecycle`, `offline-provider`) față de shim-ul vechi | 0,6% | 5,4% | 30–40 de tokeni |

O reimplementare a aceluiași API și protocol va avea în mod normal ceva peste controlul
negativ: aceleași nume Khronos, aceleași constante GL și aceleași numere de opcode.

## Etapa 2 — implementarea (`work/bridge-v2/`)

Scrisă de un agent nou, din specificație. Raportul lui spune că a deschis doar
`docs/SPEC_GLES_BRIDGE.md`, listarea folderelor ANGLE (`include`, `lib`, `bin`) și `zig.exe`,
plus propriile fișiere. Nu a deschis alte fișiere ale proiectului și nu a căutat pe web.
Asta e declarația agentului; nu e verificată tehnic.

| Parte | Fișiere | Rezultat |
|---|---|---|
| guest (`libnbtgl.so`, QNX i386) | `nbt_guest.h`, `gl_types.h`, `names.h`, `rt.c`, `virtio.c`, `dma.c`, `link.c`, `gles.c`, `egl.c`, `stubs.c`, `input.c`, `keyboard.c` | 249 de exporturi, 31 de importuri din lista permisă, fără `DT_NEEDED` |
| host (`nbt-glhost-v2.exe`) | `glh.h`, `main.c`, `logx.c`, `channel.c`, `dmaring.c`, `idle.c`, `validate.c`, `render.c`, `publish.c`, `shaders.c` | ANGLE, DMA, publicare pe fir separat, timer de 1 ms |
| autoteste | `tests/test_guest_elf.py`, `ring_harness.c`, `test_host_e2e.py` | `GUEST_ELF_PASS`, `DMA_CONTRACT_PASS`, `HOST_E2E_PASS` (29 de verificări) |

Fiecare fișier are header-ul `© 2026 davisod & JEtsKi`. Ambiguitățile din specificație și
deciziile luate (19) sunt în `work/bridge-v2/README.md`.

## Etapa 3 — verificarea

### Paritatea ANGLE reală

Testul existent (`perf-shared/test_angle_parity.py`) a fost rulat neschimbat, cu doar calea
renderer-ului înlocuită prin `work/cleanroom-audit/verify_v2.py parity`. **Trece:**

- toți cei **47.850 de octeți de răspuns** sunt identici; `reply_sha256` `7976f735…` este
  același cu al renderer-ului vechi;
- **PPM-ul complet** (1.843.216 octeți) e identic; `frame_sha256` `7ceedef1…` e același;
- **interogarea EBO** (max index 7) e corectă, iar ieșirea la EOF e curată
  (`control_eof=1 control_joined=1`), cu exit 0.

Testul de contract vechi `perf-shared/test_dma.c` nu se aplică, pentru că se compilează peste
structura internă a vechiului `dma_io.h`. Echivalentul de tip „black box” cerut de specificație
e `bridge-v2/tests/ring_harness.c`: 8 MiB în ambele direcții, wrap la 2³², limite, EOF. Trece.

### Rularea reală cu meniul

Ambele componente v2 au rulat în profil separat:
- IFS-ul implicit cu doar `boot/lib/libnbtgl.so` înlocuit, în
  `work/cleanroom-audit/ifs/walthread_keyboard_dma_v2.ifs`;
- `nbt-glhost-v2.exe`, WHPX, DMA, input nativ.

1. **Prima rulare a eșuat.** HmiMain3D a primit `SIGSEGV` la prima interogare de capabilitate a
   tastaturii. Implementatorului i s-au trimis doar observații de comportament (log-ul așteptat
   față de cel obținut), fără cod vechi.
   - **Cauza** (găsită de el): apelurile către adresele fixe din firmware erau compilate relativ
     la PC. În biblioteca preîncărcată săreau la adresa plus baza de încărcare.
   - **Corecția:** apeluri absolute, plus un test ELF care interzice această formă.
   - În aceeași iterație a fost corectat și contorul `host_to_native` din marcajul MTP.
2. **A doua rulare a trecut** (`work/cleanroom-audit/runs/run-1793364137529065200`):
   - meniul principal original e afișat;
   - tastatura e activă (`NBT_KEYBOARD_CAPABILITY … queue_ready=1`, apoi 46 de evenimente
     postate);
   - cele **4 tranziții Settings** (deschidere și înapoi, de două ori) au reușit;
   - 667 de cadre, fără crash, oprire cerută normal;
   - verificat vizual: pagina Settings și revenirea în Main menu.

| Tranziții Settings (host) | primul cadru schimbat | header stabilizat | cadre văzute pe deschidere |
|---|---:|---:|---:|
| renderer vechi de producție (`nbt-glhost-dma`) | 0,251 s | 0,937 s | 74,5 |
| vechi „fast” (`nbt-glhost-dma-fast`) | 0,181 s | 0,931 s | 78,0 |
| **v2 (clean-room, guest + host)** | **0,195 s** | 0,952 s | 81,5 |

### Similaritatea cu codul vechi

`work/cleanroom-audit/similarity.py`, k = 12 tokeni, fereastra 8. Rezultatele sunt în
`similarity_vs_old.json` și `similarity_vs_upstream.json`.

| Comparație | Amprente noi regăsite (brut) | Structural | Cea mai lungă secvență comună (brut / structural) | Linii netriviale identice |
|---|---:|---:|---:|---:|
| **v2 ↔ codul vechi (perf-guest/dma + host/perf-dma)** | **1,4%** | 10,8% | 66 / 145 de tokeni | **0** |
| **v2 ↔ qemu-mhi2 `upstream/`** | **1,1%** | 7,0% | 66 / 145 de tokeni | **0** |
| reper: derivat cunoscut (vechi ↔ qemu-mhi2) | 62,9% | 50,8% | 6.093 de tokeni | — |
| reper: cod fără legătură | 0,6% | 5,4% | 30–40 de tokeni | 0 |

Singura secvență comună lungă e tabela de valori `eglGetConfigAttrib` (constante EGL → valorile
cerute de specificație, de exemplu RED_SIZE → 8). E un fapt de interfață impus de
compatibilitate, nu cod copiat. Restul similarității structurale (7–11%) vine din tipare
inevitabile: `switch` pe opcode-uri și apeluri GL cu argumente.

## Profilul implicit (30.10, la cererea ta)

- `RUN_NBT.cmd` / `viewer.py` fără opțiuni folosesc acum v2: `work/bridge-v2/ifs/walthread_keyboard_dma_v2.ifs`
  (construit cu `work/bridge-v2/build_ifs.py`, identic byte cu byte cu imaginea verificată în
  rularea reală, sha256 `1dc9115d…`) și `work/bridge-v2/host/nbt-glhost-v2.exe`.
- Fostul profil implicit a rămas disponibil ca `--legacy`. `--fast`, `--previous`, `--software` și
  DOOM nu s-au schimbat.
- Verificări pe noul profil implicit:
  - smoke test: primul cadru, apoi închidere curată (și pentru `--legacy`);
  - testul butoanelor (`test_buttons_runtime.py`): toate cele 36 de evenimente au fost acceptate
    de HAL-ul v2, iar ecranele MEDIA / RADIO / TEL / înclinare dreapta sunt identice pixel cu pixel
    (md5) cu cele de pe stiva veche;
  - codul de ieșire 1 al viewer-ului în acel test vine de la închiderea forțată a ferestrei de
    către test: viewer-ul rămâne deschis după oprirea VM-ului, cu ultimul cadru afișat.

## Ce rămâne neschimbat (actualizat)

- Profilurile existente (`RUN_NBT.cmd`, implicit, `--previous`, `--software`, `--fast`) folosesc
  în continuare shim-ul și renderer-ele vechi, până la confirmarea ta.
- DOOM rămâne pe shim-ul vechi.

## Limite

- Separarea rolurilor e organizatorică (agenți diferiți, instrucțiuni explicite, declarații
  scrise). Nu e o izolare tehnică a sistemului de fișiere.
- Ce fișiere au fost citite e auto-declarat de agenți.
- Specificația conține, ca fapte de interfață:
  - numerele de opcode și layout-urile mesajelor;
  - numele variabilelor de mediu moștenite (`MHI2_GL_FRAME`, `MHI2_SHADER_CACHE`, …);
  - șirurile de log pe care le caută uneltele noastre.
  Acestea sunt păstrate pentru compatibilitate cu `run_hmi.py`, viewer și teste. Pot fi
  redenumite ulterior, dar asta schimbă și consumatorii.
- Acesta nu e un aviz juridic. Pentru o decizie de licențiere, raportul și specificația sunt
  dovezile de proces.
- În v2 nu am măsurat cu contoarele interne de performanță, ci doar tranzițiile văzute de host.
