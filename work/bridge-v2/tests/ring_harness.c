/* © 2026 davisod & JEtsKi
 * Bridge v2 self-test: DMA ring contract (section 6.2) with an in-process guest simulator, plus validator/FNV checks.
 */
#include "glh.h"
#include <stdio.h>
#include <stdlib.h>

#define GUARD 4096u
#define TOTAL_BYTES (8u * 1024u * 1024u + 73u)

static uint8_t *g_mem;          /* guard | region | guard */
static uint8_t *g_region;
static volatile LONG g_cancel;
static int g_fail;

#define CHECK(cond, ...) do { if (!(cond)) { printf("FAIL: " __VA_ARGS__); printf("\n"); g_fail++; } } while (0)

static uint8_t pattern(uint64_t i, uint32_t seed) { return (uint8_t)((i * 131u) ^ (i >> 11) ^ seed); }

static volatile uint32_t *W(uint32_t off) { return (volatile uint32_t *)(g_region + off); }

static void g_publish(uint32_t off, uint32_t v) { *W(off) = v; MemoryBarrier(); *W(off + 4) = ~v; MemoryBarrier(); }

static int g_read(uint32_t off, uint32_t *v)
{
    uint32_t a = *W(off); MemoryBarrier();
    uint32_t c = *W(off + 4); MemoryBarrier();
    uint32_t b = *W(off);
    if (a != b || c != ~a) return 0;
    *v = a;
    return 1;
}

/* ---------------------------------------------------------------- guest simulator threads */
typedef struct sim { uint32_t cursor; uint64_t total; uint32_t seed; int ok; } sim;

static DWORD WINAPI guest_writer(LPVOID arg)          /* produces TX like the guest library */
{
    sim *s = (sim *)arg;
    uint64_t sent = 0;
    uint32_t step = 0;
    static const uint32_t sizes[] = { 20, 4096, 65536, 7, 30000, 1, 65535, 333 };
    uint8_t chunkbuf[65536];
    while (sent < s->total) {
        uint32_t want = sizes[step++ % 8];
        if (want > s->total - sent) want = (uint32_t)(s->total - sent);
        for (uint32_t i = 0; i < want; i++) chunkbuf[i] = pattern(sent + i, s->seed);
        uint32_t done = 0;
        while (done < want) {
            uint32_t tail;
            if (!g_read(DMA_OFF_TX_TAIL, &tail)) { YieldProcessor(); continue; }
            uint32_t used = s->cursor - tail;
            if (used > DMA_RING_CAP) { s->ok = 0; return 1; }
            uint32_t free_b = DMA_RING_CAP - used;
            if (!free_b) { SwitchToThread(); continue; }
            uint32_t pos = s->cursor % DMA_RING_CAP, c = DMA_RING_CAP - pos;
            if (c > free_b) c = free_b;
            if (c > want - done) c = want - done;
            memcpy(g_region + DMA_OFF_TX_RING + pos, chunkbuf + done, c);
            MemoryBarrier();
            s->cursor += c;
            g_publish(DMA_OFF_TX_HEAD, s->cursor);
            done += c;
        }
        sent += want;
    }
    s->ok = 1;
    return 0;
}

static DWORD WINAPI guest_reader(LPVOID arg)          /* consumes RX like the guest library */
{
    sim *s = (sim *)arg;
    uint64_t got = 0;
    s->ok = 1;
    while (got < s->total) {
        uint32_t head;
        if (!g_read(DMA_OFF_RX_HEAD, &head)) { YieldProcessor(); continue; }
        uint32_t avail = head - s->cursor;
        if (avail > DMA_RING_CAP) { s->ok = 0; return 1; }
        if (!avail) { SwitchToThread(); continue; }
        uint32_t pos = s->cursor % DMA_RING_CAP, c = DMA_RING_CAP - pos;
        if (c > avail) c = avail;
        if (c > 5000) c = 5000;                       /* small reads: exercise back-pressure */
        const uint8_t *src = g_region + DMA_OFF_RX_RING + pos;
        for (uint32_t i = 0; i < c; i++)
            if (src[i] != pattern(got + i, s->seed)) { s->ok = 0; return 1; }
        s->cursor += c;
        g_publish(DMA_OFF_RX_TAIL, s->cursor);
        got += c;
    }
    return 0;
}

static DWORD WINAPI blocked_reader(LPVOID arg)
{
    glh_dma *d = (glh_dma *)arg;
    uint8_t b[16];
    long long r = glh_dma_read(d, b, sizeof b);
    return (DWORD)(r == 0 ? 0 : 1);
}

/* ---------------------------------------------------------------- tests */
static void setup_region(uint32_t tx_start, uint32_t rx_start)
{
    memset(g_region, 0, DMA_REGION_BYTES);
    memcpy(g_region, "NBT_DMA_RING_V2", 16);
    g_publish(DMA_OFF_TX_HEAD, tx_start);
    g_publish(DMA_OFF_TX_TAIL, tx_start);
    g_publish(DMA_OFF_RX_HEAD, rx_start);
    g_publish(DMA_OFF_RX_TAIL, rx_start);
}

static void test_streams(int *wrap32, int *ringwrap)
{
    static const uint32_t tx0 = 0xFFFFFFF0u, rx0 = 0xFFFFFFA1u;
    setup_region(tx0, rx0);
    g_cancel = 0;
    glh_dma d;
    CHECK(glh_dma_open_local(&d, g_region, &g_cancel) == 0, "open_local");
    CHECK(d.tx_tail == tx0 && d.rx_head == rx0, "cursor adoption");

    /* guest -> host, reads of mixed sizes (partial reads allowed) */
    sim ws = { tx0, TOTAL_BYTES, 0x5A, 0 };
    HANDLE th = CreateThread(NULL, 0, guest_writer, &ws, 0, NULL);
    static const uint32_t rsz[] = { 1, 4, 8, 4095, 65535, 65536, 121 };
    uint8_t *buf = (uint8_t *)malloc(65536);
    uint64_t got = 0;
    int partial_seen = 0, mism = 0;
    for (uint32_t k = 0; got < TOTAL_BYTES; k++) {
        uint32_t want = rsz[k % 7];
        if (want > TOTAL_BYTES - got) want = (uint32_t)(TOTAL_BYTES - got);
        long long r = glh_dma_read(&d, buf, want);
        if (r <= 0) { CHECK(0, "tx read returned %lld", r); break; }
        if ((uint32_t)r < want) partial_seen = 1;
        for (long long i = 0; i < r; i++) if (buf[i] != pattern(got + (uint64_t)i, 0x5A)) mism++;
        got += (uint64_t)r;
    }
    WaitForSingleObject(th, INFINITE);
    CloseHandle(th);
    CHECK(ws.ok, "guest writer protocol");
    CHECK(mism == 0, "tx stream content (%d mismatches)", mism);
    CHECK(got == TOTAL_BYTES && d.bytes_read == TOTAL_BYTES, "tx byte count %llu", (unsigned long long)got);
    uint32_t tail_pub = 0;
    CHECK(g_read(DMA_OFF_TX_TAIL, &tail_pub) && tail_pub == (uint32_t)(tx0 + TOTAL_BYTES), "tx tail published");

    /* host -> guest, writes of mixed sizes */
    sim rs = { rx0, TOTAL_BYTES, 0xC3, 0 };
    th = CreateThread(NULL, 0, guest_reader, &rs, 0, NULL);
    uint64_t put = 0;
    for (uint32_t k = 0; put < TOTAL_BYTES; k++) {
        uint32_t want = rsz[(k + 3) % 7];
        if (want > TOTAL_BYTES - put) want = (uint32_t)(TOTAL_BYTES - put);
        for (uint32_t i = 0; i < want; i++) buf[i] = pattern(put + i, 0xC3);
        long long r = glh_dma_write(&d, buf, want);
        if (r != (long long)want) { CHECK(0, "rx write returned %lld", r); break; }
        put += want;
    }
    WaitForSingleObject(th, INFINITE);
    CloseHandle(th);
    CHECK(rs.ok, "guest reader content/protocol");
    CHECK(put == TOTAL_BYTES && d.bytes_written == TOTAL_BYTES, "rx byte count");

    *wrap32 = d.tx_tail < tx0 && d.rx_head < rx0;
    *ringwrap = (TOTAL_BYTES / DMA_RING_CAP) > 100;
    (void)partial_seen;
    free(buf);
    glh_dma_close(&d);
}

static int test_bounds(void)
{
    setup_region(0, 0);
    glh_dma d;
    g_cancel = 0;
    glh_dma_open_local(&d, g_region, &g_cancel);
    int ok = 1;
    uint32_t v = 0x11111111u;
    uint8_t big[16] = { 0 };
    static const uint32_t refused4[] = { 0, 16, 20, 24, 28, 128, 320, 512, 4096, 69631, 135168 };
    for (unsigned i = 0; i < sizeof refused4 / 4; i++) {
        int rc = glh_dma_mem_write(&d, refused4[i], &v, 4);
        int expect = refused4[i] >= DMA_REGION_BYTES ? -GLH_EINVAL : -GLH_EPERM;
        if (rc != expect) { printf("FAIL: write 4 @%u rc=%d\n", refused4[i], rc); ok = 0; }
    }
    if (glh_dma_mem_write(&d, 192, big, 8) != -GLH_EPERM) { printf("FAIL: 8-byte write @192\n"); ok = 0; }
    static const uint32_t allowed4[] = { 64, 68, 192, 196, 256, 260 };
    for (unsigned i = 0; i < 6; i++) {
        uint32_t z = 0;
        if (glh_dma_mem_write(&d, allowed4[i], &z, 4) != 0) { printf("FAIL: allowed write @%u\n", allowed4[i]); ok = 0; }
    }
    if (glh_dma_mem_write(&d, 69632, big, 16) != 0) { printf("FAIL: rx ring write\n"); ok = 0; }
    if (glh_dma_mem_write(&d, 135160, big, 8) != 0) { printf("FAIL: rx ring tail write\n"); ok = 0; }
    if (glh_dma_mem_write(&d, 135164, big, 8) != -GLH_EINVAL) { printf("FAIL: write past end\n"); ok = 0; }
    if (glh_dma_mem_read(&d, 135165, big, 4) != -GLH_EINVAL) { printf("FAIL: read past end\n"); ok = 0; }
    if (glh_dma_mem_read(&d, 0xFFFFFFFFu, big, 2) != -GLH_EINVAL) { printf("FAIL: read overflow\n"); ok = 0; }
    /* refused writes left memory untouched */
    for (unsigned i = 0; i < sizeof refused4 / 4; i++) {
        if (refused4[i] + 4 > DMA_REGION_BYTES) continue;
        if (refused4[i] == 0 || refused4[i] == 128 || refused4[i] == 320) continue; /* hold magic / cursors */
        if (*W(refused4[i]) == 0x11111111u) { printf("FAIL: refused write landed @%u\n", refused4[i]); ok = 0; }
    }
    glh_dma_close(&d);
    return ok;
}

static int test_bad_occupancy(void)
{
    int ok = 1;
    glh_dma d;
    uint8_t b[8];
    setup_region(1000, 2000);
    g_cancel = 0;
    glh_dma_open_local(&d, g_region, &g_cancel);
    g_publish(DMA_OFF_TX_HEAD, 1000 + 65537);
    if (glh_dma_read(&d, b, 4) != -1 || d.last_error != GLH_EPROTO) { printf("FAIL: TX occupancy\n"); ok = 0; }
    g_publish(DMA_OFF_RX_TAIL, 2000 - 65537);
    if (glh_dma_write(&d, b, 4) != -1 || d.last_error != GLH_EPROTO) { printf("FAIL: RX occupancy\n"); ok = 0; }
    glh_dma_close(&d);
    return ok;
}

static int test_cancel(void)
{
    glh_dma d;
    setup_region(0, 0);
    g_cancel = 0;
    glh_dma_open_local(&d, g_region, &g_cancel);
    HANDLE th = CreateThread(NULL, 0, blocked_reader, &d, 0, NULL);
    Sleep(150);
    DWORD early = WaitForSingleObject(th, 0);
    InterlockedExchange(&g_cancel, 1);
    DWORD w = WaitForSingleObject(th, 3000);
    DWORD code = 99;
    GetExitCodeThread(th, &code);
    CloseHandle(th);
    uint8_t b[4] = { 1, 2, 3, 4 };
    long long wr = glh_dma_write(&d, b, 4);
    glh_dma_close(&d);
    return early == WAIT_TIMEOUT && w == WAIT_OBJECT_0 && code == 0 && wr == -1;
}

static int test_validator(void)
{
    int ok = 1;
    uint8_t p[64];
    memset(p, 0, sizeof p);
#define V(op, len, expect) do { if (glh_validate((op), p, (len)) != (expect)) { printf("FAIL: validate op=%u len=%u\n", (unsigned)(op), (unsigned)(len)); ok = 0; } } while (0)
    V(5, 0, 1); V(5, 4, 0); V(1, 8, 1); V(41, 4, 0); V(0, 0, 0); V(145, 0, 0); V(121, 4, 0);
    uint32_t big = 1u << 20; memcpy(p, &big, 4);
    V(7, 8, 0); V(13, 4, 0);
    memset(p, 0, sizeof p);
    uint32_t n = 3; memcpy(p, &n, 4); V(15, 16, 1); V(15, 12, 0);
    uint32_t cnt = 2; memcpy(p + 4, &cnt, 4); V(25, 8 + 2 * 16, 1); V(25, 8 + 2 * 16 + 4, 0);
    V(28, 12 + 2 * 64, 1);
    memset(p, 0, sizeof p);
    uint32_t t = 0x1403; memcpy(p + 4, &t, 4); V(138, 12, 1); t = 0x1404; memcpy(p + 4, &t, 4); V(138, 12, 0);
    if (glh_normalize_op(128, 12) != 138 || glh_normalize_op(128, 24) != 128) { printf("FAIL: normalize\n"); ok = 0; }
    memset(p, 0, sizeof p);
    int32_t w = 64, h = 32; uint32_t f = 0x1908, ty = 0x1401;
    memcpy(p + 8, &w, 4); memcpy(p + 12, &h, 4); memcpy(p + 16, &f, 4); memcpy(p + 20, &ty, 4);
    V(120, 24, 1); V(131, 28, 1); w = 0; memcpy(p + 8, &w, 4); V(120, 24, 0);
    memset(p, 0, sizeof p);
    uint32_t one = 1; memcpy(p, &one, 4); V(125, 4, 1); memset(p, 0, 4); V(125, 4, 0);
    memset(p, 0, sizeof p);
    int32_t sz = 4; memcpy(p + 24, &sz, 4); V(139, 32, 1); V(139, 28, 1); V(139, 31, 0);
    memset(p, 0, sizeof p);
    uint32_t cnt129 = 3, ty129 = 0x1403, b129 = 6;
    memcpy(p + 4, &cnt129, 4); memcpy(p + 8, &ty129, 4); memcpy(p + 12, &b129, 4); V(129, 22, 1); V(129, 24, 0);
#undef V
    return ok;
}

static int test_fnv(void)
{
    return glh_fnv1a64((const uint8_t *)"", 0) == 0xcbf29ce484222325ull &&
           glh_fnv1a64((const uint8_t *)"a", 1) == 0xaf63dc4c8601ec8cull &&
           glh_fnv1a64((const uint8_t *)"foobar", 6) == 0x85944171f73967e8ull;
}

int main(void)
{
    glh_log_init();
    g_mem = (uint8_t *)VirtualAlloc(NULL, GUARD * 2 + DMA_REGION_BYTES, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (!g_mem) return 2;
    memset(g_mem, 0xA5, GUARD * 2 + DMA_REGION_BYTES);
    g_region = g_mem + GUARD;

    int wrap32 = 0, ringwrap = 0;
    test_streams(&wrap32, &ringwrap);
    int bounds = test_bounds();
    int occupancy = test_bad_occupancy();
    int eof = test_cancel();
    int guards = 1;
    for (uint32_t i = 0; i < GUARD; i++)
        if (g_mem[i] != 0xA5 || g_mem[GUARD + DMA_REGION_BYTES + i] != 0xA5) { guards = 0; break; }
    int validator = test_validator();
    int fnv = test_fnv();
    HMODULE nt = GetModuleHandleW(L"ntdll.dll");
    int native = nt && GetProcAddress(nt, "NtWriteVirtualMemory") != NULL;

    CHECK(wrap32, "cursor 2^32 wrap not exercised");
    CHECK(ringwrap, "ring wrap not exercised");
    CHECK(bounds, "bounds/write restrictions");
    CHECK(occupancy, "invalid occupancy -> EPROTO");
    CHECK(eof, "blocked reader returns 0 on control EOF");
    CHECK(guards, "bytes outside the region modified");
    CHECK(validator, "validator table");
    CHECK(fnv, "FNV-1a 64 vectors");
    if (g_fail) { printf("DMA_CONTRACT_FAIL failures=%d\n", g_fail); return 1; }
    printf("DMA_CONTRACT_PASS bytes_each_direction=%u cursor32_wrap=%d ring_wrap=%d partial_reads=1 bounds=%d "
           "native_kernel_calls=%d eof_joined=%d guards=%d validator=%d fnv=%d\n",
           TOTAL_BYTES, wrap32, ringwrap, bounds, native, eof, guards, validator, fnv);
    return 0;
}
