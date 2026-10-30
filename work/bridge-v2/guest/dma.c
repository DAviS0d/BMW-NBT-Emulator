/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): DMA ring region (header, cursors, send/recv) and op 144 bootstrap.
 */
#include "nbt_guest.h"

#define REGION_BYTES   135168u
#define RING_CAP       65536u
#define OFF_ATTACHED   64u
#define OFF_STOP       68u
#define OFF_TX_HEAD    128u
#define OFF_TX_TAIL    192u
#define OFF_RX_HEAD    256u
#define OFF_RX_TAIL    320u
#define OFF_TX_RING    4096u
#define OFF_RX_RING    69632u
#define WAIT_TIMEOUT_NS 10000000000ull

static volatile uint8_t *g_region;
static uint32_t g_region_phys;
static uint32_t g_tx_head;   /* guest-owned cursors (local copies) */
static uint32_t g_rx_tail;

static inline volatile uint32_t *word(uint32_t off) { return (volatile uint32_t *)(g_region + off); }

static void publish(uint32_t off, uint32_t v)
{
    *word(off) = v;
    nbt_mb();
    *word(off + 4) = ~v;
    nbt_mb();
}

/* 1 = valid read, 0 = publication in progress */
static int read_cursor(uint32_t off, uint32_t *out)
{
    uint32_t a = *word(off);
    nbt_mb();
    uint32_t c = *word(off + 4);
    nbt_mb();
    uint32_t b = *word(off);
    if (a != b || c != ~a) return 0;
    *out = a;
    return 1;
}

typedef struct waiter { uint32_t it; uint64_t start; } waiter;

static void wait_reset(waiter *w) { w->it = 0; w->start = 0; }

/* One idle iteration. Returns -1 when the wait must fail. */
static int wait_step(waiter *w)
{
    if (*word(OFF_STOP) != 0) {
        NBT_LOG("NBT_DMA_HOST_STOPPED\n");
        return -1;
    }
    nbt_pause();
    w->it++;
    if (w->it % 65536u == 0) {
        uint64_t now = nbt_monotonic_ns();
        if (w->start == 0) w->start = now ? now : 1;
        else if (now > w->start && now - w->start > WAIT_TIMEOUT_NS) {
            NBT_LOG("NBT_DMA_WAIT_TIMEOUT\n");
            return -1;
        }
        usleep(1000);
    }
    return 0;
}

int nbt_dma_send(const void *p, uint32_t n)
{
    const uint8_t *src = (const uint8_t *)p;
    waiter w;
    wait_reset(&w);
    while (n > 0) {
        uint32_t tail;
        if (!read_cursor(OFF_TX_TAIL, &tail)) { if (wait_step(&w)) return -1; continue; }
        uint32_t used = g_tx_head - tail;
        if (used > RING_CAP) abort();
        uint32_t free_b = RING_CAP - used;
        if (free_b == 0) { if (wait_step(&w)) return -1; continue; }
        uint32_t pos = g_tx_head % RING_CAP;
        uint32_t chunk = RING_CAP - pos;
        if (chunk > free_b) chunk = free_b;
        if (chunk > n) chunk = n;
        memcpy((void *)(g_region + OFF_TX_RING + pos), src, chunk);
        nbt_mb();
        g_tx_head += chunk;
        publish(OFF_TX_HEAD, g_tx_head);
        src += chunk;
        n -= chunk;
        wait_reset(&w);
        }
    return 0;
}

int nbt_dma_recv(void *p, uint32_t n)
{
    uint8_t *dst = (uint8_t *)p;
    waiter w;
    wait_reset(&w);
    while (n > 0) {
        uint32_t head;
        if (!read_cursor(OFF_RX_HEAD, &head)) { if (wait_step(&w)) return -1; continue; }
        uint32_t avail = head - g_rx_tail;
        if (avail > RING_CAP) return -1;
        if (avail == 0) { if (wait_step(&w)) return -1; continue; }
        uint32_t pos = g_rx_tail % RING_CAP;
        uint32_t chunk = RING_CAP - pos;
        if (chunk > avail) chunk = avail;
        if (chunk > n) chunk = n;
        nbt_mb();
        memcpy(dst, (const void *)(g_region + OFF_RX_RING + pos), chunk);
        nbt_mb();
        g_rx_tail += chunk;
        publish(OFF_RX_TAIL, g_rx_tail);
        dst += chunk;
        n -= chunk;
        wait_reset(&w);
        }
    return 0;
}

int nbt_dma_bootstrap(void)
{
    uint32_t phys = 0;
    uint8_t *r = (uint8_t *)nbt_dma_alloc(REGION_BYTES, &phys);
    if (!r) return -1;
    g_region = r;
    g_region_phys = phys;

    static const char magic[16] = "NBT_DMA_RING_V2";   /* 15 chars + NUL */
    memcpy(r, magic, 16);
    uint32_t hdr[3] = { 2u, REGION_BYTES, RING_CAP };
    memcpy(r + 16, hdr, 12);
    uint64_t ns = nbt_monotonic_ns();
    uint32_t nonce[4];
    nonce[0] = (uint32_t)getpid();
    nonce[2] = (uint32_t)ns;
    nonce[1] = phys ^ nonce[2];
    nonce[3] = (uint32_t)(ns >> 32);
    memcpy(r + 28, nonce, 16);
    g_tx_head = 0;
    g_rx_tail = 0;
    publish(OFF_TX_HEAD, 0);
    publish(OFF_TX_TAIL, 0);
    publish(OFF_RX_HEAD, 0);
    publish(OFF_RX_TAIL, 0);

    uint8_t msg[36];
    uint32_t f[5] = { 144u, 28u, phys, REGION_BYTES, 2u };
    memcpy(msg, f, 20);
    memcpy(msg + 20, r + 28, 16);
    if (nbt_port1_send(msg, 36) != 0) return -1;

    uint8_t ack[8];
    uint32_t len = 0, val = 0;
    if (nbt_port1_recv(ack, sizeof ack, &len) != 0) return -1;
    if (len != 4) return -1;
    memcpy(&val, ack, 4);
    nbt_mb();
    if (val != 1 || *word(OFF_ATTACHED) != 1) return -1;
    nbt_port1_repost();
    NBT_LOG("NBT_DMA_TRANSPORT_READY physical=0x%x bytes=135168 capacity=65536 original_stream=1\n", phys);
    return 0;
}
