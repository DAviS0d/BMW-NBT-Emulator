# Raport: ecranul de pornire (animația / logo-ul M) — 30 octombrie 2026

Doar analiză, fără nicio modificare de firmware. Analiza se reface cu
`py -3 work/startup-analysis/audit_startup.py`; ieșirea e salvată în
`work/startup-analysis/audit_output.txt`.

## Pe scurt

- **Codarea ta cere animația cu logo M.** `STARTUP_TYPE` = animation, `STARTUP_EMBLEM` =
  variant_01, `HMI_BRAND` = bmw.
- **Animația nu o desenează `HmiMain3D`.** O desenează aplicația separată **EVA (Early Video
  Application)**, componenta `CPEarlyVideoControlDevImpl` din `opt/car/bin/NBTCarHUOne`.
  HMI-ul doar se coordonează cu ea prin MOST: se ascunde cât rulează EVA, apoi îi cere oprirea.
- **De ce emulatorul o sare:** imaginea IFS a emulatorului nu pornește `NBTCarHUOne`, deci
  FBlock-ul EVA nu există. HMI-ul vede „EVA Proxy not active” și trece direct la meniu.
- **Resursele există în firmware-ul extras:** `opt/car/data/eva/images` conține imaginea fixă
  `eva_splash_0x01_10.png` (logo M, 1280×480) și animația `eva_ani_0x01_10.pdds` (149 de
  cadre, format NVIDIA comprimat).
- **Rularea cerută nu e realistă acum.** Niciun semnal trimis HMI-ului nu produce animația,
  pentru că HMI-ul nu o conține. Pentru a rula EVA ar trebui emulată stiva grafică NVIDIA
  nativă. Nu am făcut rularea. Variantele posibile sunt la final.

## 1. Codarea (CAFD / NCD-ul tău)

Descriptorii sunt compilați în `HmiMain3D`: tabela `0x09879ea8`, schema din
`syset-native/hmi_native_coding_schema.json`. Valorile sunt citite din segmentele NCD
furnizate (`work/graphics-port/coding-input/segment_3001xx.bin`):

| Parametru | Bloc / octet / mască | Octet brut | Valoare la tine | Variante |
|---|---|---|---|---|
| `STARTUP_TYPE` | `3001` / 62 / `0x06` | `0x0c` | **2 = animation** | 0 black, 1 splash, 2 animation |
| `STARTUP_EMBLEM` | `3001` / 62 / `0x78` | `0x0c` | **1 = variant_01 (M)** | variant_00 … variant_09 |
| `HMI_BRAND` | `3000` / 133 / `0x3c` | `0x41` | 0 = bmw | bmw, bmw_i, mini, rr, nev |
| `STARTUP` | `3003` / 15 / `0x40` | `0xbe` | 0 = nicht_aktiv | |
| `WELCOME_LIGHT` | `3000` / 92 / `0x20` | `0x6c` | 1 = activ | |
| `EARLY_VIDEO_LEGALDISCL` | `3001` / 19 | `0x00` | initwert | |

Semnificația variantelor vine din numele resurselor `eva_splash_0x<emblemă>_<07|10>.png`, unde
07/10 = ecranul de 7" sau 10,25". **`0x01` = logo-ul M** (pe fundal, o pistă cu linii roșii) și
**`0x00` = „BMW ConnectedDrive”**. Le-am verificat vizual. Celelalte variante (02–09) nu le-am
etichetat.

`STARTUP_EMBLEM`, `STARTUP_TYPE` și `DISPLAY_VARIANTE` apar ca chei de codare în
`opt/sys/bin/VideoApp`. Clientul Syset al acestuia (`CEarlyIntelSysetClientConfigImpl`) le
citește pentru partea „early”. Aceleași chei apar și în aplicația Jacinto.

## 2. Cine afișează animația și ce o declanșează

### EVA: `NBTCarHUOne` / `CPEarlyVideoControlDevImpl`

Lanțul reconstruit din șirurile și din FSM-ul `CEarlyVideoApplicationFSM`:

1. `copyStartupImage` copiază fișierul potrivit codării în directorul de date EVA („copying
   file %s to the EVA data dir (emblem %x; type %x)”).
2. Grafica pornește („Early Video: kdInitializeNV”, fir WAL) și ajunge în starea `graphicReady`.
3. FBlock-ul MOST **SystemFunction** trimite „Power State is ON” și `UserMonitor`, apoi
   `OkayFromUserMonitor`. Pe mașină asta înseamnă pornirea unității sau ecranului, adică
   contact / borna 15 sau „monitor ON”.
4. Starea `InitOkay` duce la `startWAPlayback`:
   - type = animation: „start playing welcome animation” (`eva_ani_*.pdds`);
   - type = splash: „show splash screen” (`eva_splash_*.png`);
   - altfel: ecran negru.
   O cerere de cameră aflată deja în coadă are prioritate: „Welcome animation wasn't started
   due to queued camera request”.
5. Oprirea vine prin proprietatea MOST `EarlyVideoApplicationStatus`, setată la
   „shutdown”/„terminate” de HMI. După `EVAS_Stopped`, HMI-ul comută stratul EVA→HMI.

Nu am găsit o condiție „deschiderea ușii / welcome” separată pentru acest ecran. `WELCOME_LIGHT`
e codarea pentru lumini, nu pentru ecran. Declanșatorul e pornirea unității cu monitorul
pornit. Asta e o deducție din șiruri, neverificată prin dezasamblare completă.

### HMI (`HmiMain3D`)

Șirurile `[EVA]` (`CHmiAppProcUnit::onEarlyVideoFBlockActivate`,
`onEarlyVideoApplicationStatus`, `sendEarlyVideoShutdown`):

- Dacă `eva_EARLY_VIDEO_ENABLED` e activ (flag intern de pornire, nu parametru de codare) și
  FBlock-ul EVA răspunde, HMI-ul notează: „EVA is running, disabling HMI updates”, „rendering
  hidden HMI frame”.
- Apoi trimite „sending EVA shutdown” și, la `EVAS_Stopped`, face „switch layers EVA->HMI”.
- Dacă FBlock-ul EVA lipsește: „**EVA Proxy not active -> resuming HMI updates**”, adică
  meniul apare imediat.

### De ce emulatorul o sare

Scriptul de pornire al IFS-urilor din emulator pornește `devb-ram`, `pipe`, `mqueue`,
`slogger`, `io-pkt`, `servicebroker`, `BMWOTFagent`, `watchdog`, `most`, `mtp2most` și
`HmiMain3D`. **Nu pornește `NBTCarHUOne`.** `appimage.ifs` original nu îl conține: aplicația
stă în `sda0/repository/istep/opt/car/bin`. Fără EVA, HMI-ul ia ramura „EVA Proxy not active”
și desenează direct meniul. În emulator, trace-urile `[EVA]` nu se văd, pentru că profilul
OTF quiet le filtrează.

## 3. Resursele

`outputs/NBT_files/00001e6b/Intel/fs/sda0/repository/istep/opt/car/data/eva/images/`:

| Fișier | Ce e |
|---|---|
| `eva_splash_0x00..0x09_{07,10}.png` | imagini fixe per emblemă (07 = 7", 10 = 10,25") |
| `eva_ani_0x00..0x09_{07,10}.pdds` | animațiile; pentru tine `eva_ani_0x01_10.pdds`, 4,3 MB |
| `eva_side_*`, `eva_uview_*`, `eva_rear_*` | grafica pentru camere (side/top/rear view) |

Formatul `.pdds`:
- antet DDS cu magic `PDDS` și marcajul `NVTT`, format **DXT1**, 1280×480;
- câmpul mipmap = **149**, adică cadrele animației;
- datele sunt pe blocuri `HEAD`, comprimate cu un codec propriu (nu zlib, entropie 7,35).
  Le decodează EVA. 149 de cadre DXT1 necomprimate ar avea ~45 MB.

## 4. De ce nu am făcut rularea

- Să trimit HMI-ului starea „EVA running” (simulând FBlock-ul EVA prin serviciile MOST
  emulate) e posibil. Efectul însă ar fi doar că HMI-ul își ascunde cadrele până la
  `EVAS_Stopped`: **ecran negru, apoi meniul.** Animația nu ar apărea, pentru că nu o
  desenează nimeni.
- `NBTCarHUOne` cere stiva grafică NVIDIA nativă: `libKD` (`kdInitializeNV`), `libEGL`,
  `libGLESv2_CM`, `libnvsys`, `libnvgpu`, `libnvrmsys`, `libnvblt`, `libwal_nvidia`. Cere și
  framework-ul MOST/DSI (`libSysMoCCAFramework…`, `libimp_sys_most_base_nbt`,
  servicebroker), plus clientul Syset „early” cu emblema. Shim-ul nostru acoperă doar
  EGL/GLES pentru `HmiMain3D` și un WAL în proces. Ar fi un proiect de portare separat, nu o
  rulare.

## Variante pentru pasul următor

1. **Simplu, fidel doar ca imagine.** Viewer-ul afișează `eva_splash_0x<emblemă>_10.png` din
   firmware de la pornirea VM-ului până la primul cadru HMI. Emblema se alege din codarea ta
   (`STARTUP_EMBLEM` = 1, adică M). Folosește resursa originală, dar e o imagine fixă, nu
   animația, și nu respectă exact `STARTUP_TYPE`. Efort mic.
2. **Animația reală, redată de viewer.** Reconstruirea decodorului `.pdds` (blocurile `HEAD`)
   din `NBTCarHUOne` prin dezasamblare, conversia offline a celor 149 de cadre și redarea lor
   în viewer în timpul pornirii. Fidel vizual, efort mediu: reverse engineering pe un singur
   decodor.
3. **EVA originală în emulator.** Pornirea `NBTCarHUOne` într-un IFS separat, cu
   emularea/adaptarea KD/nvblt/WAL-NVIDIA și a FBlock-urilor MOST (SystemFunction,
   VideoConnectionMaster, EarlyVideo). Cea mai fidelă, efort mare.

Recomandarea mea e 2, eventual cu 1 ca primă etapă.

## Limite

- `VideoApp` și resursele EVA vin din SWFL `00001e6b`, iar `NBTCarHUOne` din BTLD
  `00001275`. Nu am verificat dacă sunt exact perechea instalată cu `003_009_004`.
- `STARTUP` (bloc 3003, nicht_aktiv) nu are legătură clară cu EVA. Nu l-am urmărit în cod.
- Fluxul EVA e reconstruit din șiruri și din numele stărilor FSM, fără dezasamblarea completă
  a `CPEarlyVideoControlDevImpl`.

---

# Implementare (30.10, după-amiază): variantele 1 și 2

## Pasul 1 — imaginea fixă aleasă din codare (commit `bbf5a2d`)

`work/startup-analysis/startup_screen.py`:

- citește NCD-ul (`NBT_NCD`, implicit `C:\Data\CAF\CAFD_00000DED_003_012_025.ncd`) ca
  S-records, cu verificarea checksum-ului;
- citește `STARTUP_TYPE` și `STARTUP_EMBLEM` la pozițiile (bloc, octet, mască) din schema
  descriptorilor compilați în `HmiMain3D`, nu din valori scrise de mână;
- alege din `opt/car/data/eva/images` fișierul `eva_splash_0x<emblemă>_*.png` cu dimensiunile
  ecranului emulat, 1280×480.

În `viewer.py`, la pornire:

- `black` → ecran negru;
- `splash` → imaginea fixă;
- `animation` → cadrele animației, apoi imaginea fixă.

Ecranul de pornire rămâne afișat până la **primul cadru HMI cu conținut**. Cadrul gol inițial
al renderer-ului și cadrele HMI negre sunt sărite: diferența dintre pixelii eșantionați trebuie
să fie peste 24.

Verificat: smoke `--fast`. Splash-ul apare la 0,03 s, iar la 13,6 s e înlocuit de meniul
principal real.

## Pasul 2 — decodorul `.pdds` și animația

`work/startup-analysis/pdds.py`, Python pur, fără dependențe. Formatul a fost stabilit
din fișiere, fără documentație:

| Element | Conținut |
|---|---|
| antet | `PDDS` + antet DDS de 124 de octeți: NVTT, FourCC `DXT1`, 1280×480, `mipMapCount` = număr de cadre (149), `pitchOrLinearSize` = 307.200 (un cadru DXT1) |
| cadre | 149 de bucăți `HEAD` + u32 lungime, câte una pe cadru, care acoperă exact fișierul |
| comprimare | fiecare bucată e un flux **LZO1X** (decodor reimplementat după algoritmul minilzo `lzo1x_d`) |
| cadrul 0 (cheie) | după LZO: exact 307.200 de octeți = 38.400 de blocuri DXT1 (4×4 pixeli) |
| cadrele 1–148 (delta) | după LZO: câte un cod pe bloc, în ordinea rândurilor: `0x00` + 8 octeți = bloc nou; `0x80`–`0xff` = copiază blocul din cadrul precedent de la (dx, dy) = ((cod & 15) − 7, ((cod >> 4) & 7) − 3); `0xb7` = neschimbat |

Validare:

- toate cele 148 de cadre delta au exact 38.400 de coduri și nu lasă octeți rămași;
- nicio referință nu iese din cadru;
- coduri `0x01`–`0x7f` nu apar;
- ultimul cadru (148) e, vizual, imaginea `eva_splash_0x01_10.png`: animația se termină pe
  imaginea fixă, ca pe mașină;
- decodarea completă durează ~22 s, cu un cache pe blocurile DXT1.

Animația (`eva_ani_0x01_10.pdds`): orizontul se aprinde, liniile pistei devin roșii, iar logo-ul
M apare și se clarifică.

Cadrele PNG ajung în `work/startup-analysis/frames/eva_ani_0x<emblemă>/` (~17 MB). Sunt
derivate din firmware, deci stau în `.gitignore`. Se generează:

- automat, de viewer, în fundal, la prima pornire în care lipsesc. Acea pornire arată doar
  imaginea fixă; de la următoarea rulează animația;
- sau manual: `py -3 work/startup-analysis/startup_screen.py --prepare`. Scrierea se face
  într-un folder temporar redenumit la final, deci o decodare întreruptă nu e folosită.

Viewer-ul încarcă fiecare cadru abia când îl afișează, deci fereastra nu se blochează.

Verificat:

- smoke `--fast`: `startup_screen_shown` la 0,04 s (149 de cadre),
  `startup_animation_finished` la 7,33 s, imaginea fixă până la
  `startup_screen_replaced_by_hmi` la 13,63 s;
- `--prepare` după ștergerea cadrelor reproduce aceleași 149 de PNG-uri (md5 identic);
- `STARTUP_TYPE` black și splash au fost testate cu copii ale NCD-ului cu octetul modificat (în
  scratchpad, NCD-ul tău neatins): `black` → fără imagine, `splash` → imaginea fixă, fără
  animație.

## Limite

- **Ritmul:** fișierul `.pdds` nu conține rata de redare. Am folosit 40 ms pe cadru (25 fps),
  dar efectiv a ieșit ~49 ms, pentru că decodarea PNG în Tk e uneori mai lentă. Pe mașină,
  ritmul poate fi altul.
- **Durata:** EVA pe mașină se oprește când HMI-ul îi cere (`EVAS_Stopped`). În viewer,
  echivalentul e primul cadru HMI cu conținut.
- **Ecranul de 7":** emblema și tipul se citesc din codare, dar dimensiunea e fixată la
  ecranul emulat de 1280×480 (fișierele `_10`). Codarea 7" (`DISPLAY_VARIANTE`) nu e folosită.
- **Variantele 02–09:** decodorul le acceptă, dar nu le-am verificat vizual.
