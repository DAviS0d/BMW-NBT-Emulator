/* Â© 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): userspace legacy virtio-console driver (PCI scan, vrings, MULTIPORT control).
 */
#include "nbt_guest.h"

#define VREG_HOST_FEATURES  0
#define VREG_GUEST_FEATURES 4
#define VREG_QUEUE_PFN      8
#define VREG_QUEUE_SIZE     12
#define VREG_QUEUE_SEL      14
#define VREG_QUEUE_NOTIFY   16
#define VREG_STATUS         18
#define VREG_ISR            19

#define WAIT_SLEEP_EVERY    65536u
#define WAIT_LIMIT          800000000u
#define CTRL_SLEEP_EVERY    4096u
#define CTRL_LIMIT          50000000u
#define CTRL_SLOT_BYTES     256u

typedef struct vdesc { uint32_t addr_lo, addr_hi, len; uint16_t flags, next; } vdesc;
typedef struct vused { uint32_t id, len; } vused;

typedef struct vring_q {
    uint32_t index, n;
    uint32_t phys;
    volatile vdesc *desc;
    volatile uint16_t *avail;      /* [0]=flags [1]=idx [2..]=ring */
    volatile uint16_t *used;       /* [0]=flags [1]=idx, ring follows at +4 */
    uint16_t submitted, completed;
    /* perf statistics (section 2.13) */
    uint32_t st_completed, st_immediate, st_timeouts, st_max;
    uint64_t st_spins, st_sleeps;
    int ready;
} vring_q;

static uint16_t g_io;              /* BAR0 I/O base, 0 = device not found */
static vring_q g_q[8];
static uint8_t *g_ctrl_rx, *g_ctrl_tx;  static uint32_t g_ctrl_rx_phys, g_ctrl_tx_phys, g_ctrl_slots;
static uint8_t *g_p2_rx, *g_p2_tx;      static uint32_t g_p2_rx_phys, g_p2_tx_phys;
static uint8_t *g_p1_rx, *g_p1_tx;      static uint32_t g_p1_rx_phys, g_p1_tx_phys;
static uint32_t g_alloc_seq;

static inline volatile vused *used_ring(vring_q *q) { return (volatile vused *)(q->used + 2); }

/* ---------------------------------------------------------------- DMA memory */
void *nbt_dma_alloc(uint32_t bytes, uint32_t *phys_out)
{
    uint32_t len = (bytes + 4095u) & ~4095u;
    void *p = mmap64((void *)0, len, QNX_PROT_RW, QNX_MAP_PHYS_ANON, QNX_NOFD, 0);
    if (p == (void *)-1 || p == (void *)0) {
        NBT_LOG("VIRTIO_DMA_MMAP_FAIL bytes=%u\n", bytes);
        return (void *)0;
    }
    int64_t phys = 0;
    size_t contig = 0;
    int rc = mem_offset64(p, QNX_NOFD, len, &phys, &contig);
    g_alloc_seq++;
    NBT_LOG("VIRTIO_DMA_ALLOC n=%u virtual=%p physical=0x%llx bytes=%u contiguous=%u rc=%d\n",
            g_alloc_seq, p, (unsigned long long)phys, bytes, (unsigned)contig, rc);
    if (rc != 0 || phys <= 0 || (uint64_t)phys + len > 0x100000000ull || (phys & 4095) != 0 || contig < len)
        return (void *)0;
    memset(p, 0, len);
    *phys_out = (uint32_t)phys;
    return p;
}

/* ---------------------------------------------------------------- PCI */
static uint32_t pci_read(uint32_t addr, uint32_t reg)
{
    io_out32(0xCF8, addr | reg);
    return io_in32(0xCFC);
}

static void pci_write(uint32_t addr, uint32_t reg, uint32_t v)
{
    io_out32(0xCF8, addr | reg);
    io_out32(0xCFC, v);
}

/* ---------------------------------------------------------------- vrings */
static int vq_setup(uint32_t idx)
{
    vring_q *q = &g_q[idx];
    io_out16(g_io + VREG_QUEUE_SEL, (uint16_t)idx);
    uint32_t n = io_in16(g_io + VREG_QUEUE_SIZE);
    if (n == 0 || (n & (n - 1)) != 0 || n > 32768) return -1;
    uint32_t avail_bytes = 6 + 2 * n;
    uint32_t used_off = (16 * n + avail_bytes + 4095u) & ~4095u;
    uint32_t total = (used_off + 6 + 8 * n + 4095u) & ~4095u;
    uint32_t phys = 0;
    uint8_t *mem = (uint8_t *)nbt_dma_alloc(total, &phys);
    if (!mem) return -1;
    q->index = idx;
    q->n = n;
    q->phys = phys;
    q->desc = (volatile vdesc *)mem;
    q->avail = (volatile uint16_t *)(mem + 16 * n);
    q->used = (volatile uint16_t *)(mem + used_off);
    q->avail[0] = 1;                 /* VRING_AVAIL_F_NO_INTERRUPT */
    nbt_mb();
    io_out32(g_io + VREG_QUEUE_PFN, phys >> 12);
    uint32_t rb = io_in32(g_io + VREG_QUEUE_PFN);
    NBT_LOG("VIRTIO_QUEUE index=%u count=%u bytes=%u pfn=0x%x readback=0x%x\n", idx, n, total, phys >> 12, rb);
    q->ready = 1;
    return 0;
}

static void vq_notify(vring_q *q) { io_out16(g_io + VREG_QUEUE_NOTIFY, (uint16_t)q->index); }

/* Data queues: exactly one buffer in flight, always descriptor 0. */
static void vq_post_ex(vring_q *q, uint32_t phys, uint32_t len, int device_writes, int notify)
{
    q->desc[0].addr_lo = phys;
    q->desc[0].addr_hi = 0;
    q->desc[0].len = len;
    q->desc[0].flags = device_writes ? 2 : 0;
    q->desc[0].next = 0;
    q->avail[2 + (q->submitted % q->n)] = 0;
    nbt_mb();
    q->submitted++;
    q->avail[1] = q->submitted;
    nbt_mb();
    if (notify) vq_notify(q);
}

static void vq_post(vring_q *q, uint32_t phys, uint32_t len, int device_writes)
{
    vq_post_ex(q, phys, len, device_writes, 1);
}

/* Blocking completion wait (section 4.1). Returns 0 and the used length, -1 on error. */
static int vq_wait(vring_q *q, uint32_t *len_out)
{
    uint32_t it = 0;
    for (;;) {
        nbt_mb();
        uint16_t u = q->used[1];
        if (u != q->completed) {
            volatile vused *e = &used_ring(q)[q->completed % q->n];
            uint32_t id = e->id, len = e->len;
            q->completed++;
            q->st_completed++;
            if (it == 0) q->st_immediate++;
            q->st_spins += it;
            q->st_sleeps += it / WAIT_SLEEP_EVERY;
            if (it > q->st_max) q->st_max = it;
            if (id != 0) return -1;
            if (len_out) *len_out = len;
            return 0;
        }
        it++;
        nbt_pause();
        if (it % WAIT_SLEEP_EVERY == 0) usleep(1000);
        if (it >= WAIT_LIMIT) {
            q->st_timeouts++;
            q->st_spins += it;
            q->st_sleeps += it / WAIT_SLEEP_EVERY;
            if (it > q->st_max) q->st_max = it;
            NBT_LOG("VIRTIO_WAIT_TIMEOUT queue=%u submitted=%u vfast_complete=%u used=%u status=%u isr=%u\n",
                    q->index, (unsigned)q->submitted, (unsigned)q->completed, (unsigned)u,
                    (unsigned)io_in8(g_io + VREG_STATUS), (unsigned)io_in8(g_io + VREG_ISR));
            return -1;
        }
    }
}

/* ---------------------------------------------------------------- control queue (2 RX / 3 TX) */
static void ctrl_post_slot(uint32_t slot)
{
    vring_q *q = &g_q[2];
    q->desc[slot].addr_lo = g_ctrl_rx_phys + slot * CTRL_SLOT_BYTES;
    q->desc[slot].addr_hi = 0;
    q->desc[slot].len = CTRL_SLOT_BYTES;
    q->desc[slot].flags = 2;
    q->desc[slot].next = 0;
    q->avail[2 + (q->submitted % q->n)] = (uint16_t)slot;
    nbt_mb();
    q->submitted++;
    q->avail[1] = q->submitted;
    nbt_mb();
}

static int ctrl_send(uint32_t id, uint16_t event, uint16_t value)
{
    uint8_t *m = g_ctrl_tx;
    memcpy(m, &id, 4);
    memcpy(m + 4, &event, 2);
    memcpy(m + 6, &value, 2);
    vq_post(&g_q[3], g_ctrl_tx_phys, 8, 0);
    int rc = vq_wait(&g_q[3], (uint32_t *)0);
    NBT_LOG("VIRTIO_CONTROL_SEND id=%u event=%u value=%u\n", id, (unsigned)event, (unsigned)value);
    return rc;
}

/* Receives one control message into msg (NUL terminated). Returns length or -1. */
static int ctrl_recv(uint8_t *msg)
{
    vring_q *q = &g_q[2];
    uint32_t it = 0;
    for (;;) {
        nbt_mb();
        uint16_t u = q->used[1];
        if (u != q->completed) {
            volatile vused *e = &used_ring(q)[q->completed % q->n];
            uint32_t id = e->id, len = e->len;
            q->completed++;
            q->st_completed++;
            if (it == 0) q->st_immediate++;
            q->st_spins += it;
            if (it > q->st_max) q->st_max = it;
            if (id >= g_ctrl_slots || len < 8 || len > CTRL_SLOT_BYTES) {
                NBT_LOG("VIRTIO_CONTROL_INVALID id=%u length=%u\n", id, len);
                return -1;
            }
            memcpy(msg, g_ctrl_rx + id * CTRL_SLOT_BYTES, len);
            msg[len] = 0;
            ctrl_post_slot(id);
            vq_notify(q);
            return (int)len;
        }
        it++;
        nbt_pause();
        if (it % CTRL_SLEEP_EVERY == 0) usleep(1000);
        if (it >= CTRL_LIMIT) {
            q->st_timeouts++;
            NBT_LOG("VIRTIO_CONTROL_TIMEOUT submitted=%u complete=%u used=%u\n",
                    (unsigned)q->submitted, (unsigned)q->completed, (unsigned)u);
            return -1;
        }
    }
}

typedef struct port_state { int acked, named, open; } port_state;

static int control_handshake(void)
{
    static const char *const expected[3] = { "", "nbtgl", "nbtinput" };
    port_state ps[3];
    uint8_t msg[CTRL_SLOT_BYTES + 1];
    memset(ps, 0, sizeof ps);
    if (ctrl_send(0xFFFFFFFFu, 0, 1) != 0) return -1;
    for (int count = 0; count < 128; count++) {
        int len = ctrl_recv(msg);
        if (len < 0) return -1;
        uint32_t id; uint16_t ev, val;
        memcpy(&id, msg, 4); memcpy(&ev, msg + 4, 2); memcpy(&val, msg + 6, 2);
        NBT_LOG("VIRTIO_CONTROL_RECEIVE id=%u event=%u value=%u\n", id, (unsigned)ev, (unsigned)val);
        if (id != 1 && id != 2) continue;
        port_state *p = &ps[id];
        switch (ev) {
        case 1: /* DEVICE_ADD */
            if (val != 0 && !p->acked) {
                p->acked = 1;
                if (ctrl_send(id, 3, 1) != 0) return -1;
                if (ctrl_send(id, 6, 1) != 0) return -1;
            }
            break;
        case 7: { /* PORT_NAME */
            const char *name = (const char *)(msg + 8);
            if (strcmp(name, expected[id]) != 0) {
                NBT_LOG("VIRTIO_CONTROL_WRONG_PORT_NAME id=%u name=%s expected=%s\n", id, name, expected[id]);
                return -1;
            }
            NBT_LOG("VIRTIO_CONTROL_PORT_NAME id=%u name=%s\n", id, name);
            p->named = 1;
            break;
        }
        case 6: /* PORT_OPEN from host */
            p->open = val != 0;
            break;
        case 2: /* DEVICE_REMOVE */
            NBT_LOG("VIRTIO_CONTROL_PORT_REMOVED id=%u\n", id);
            return -1;
        default:
            break;
        }
        if (ps[1].acked && ps[1].named && ps[1].open && ps[2].acked && ps[2].named && ps[2].open) {
            NBT_LOG("VIRTIO_FLOW_CONTROLLED_PORT_READY id=1 rx_queue=4 tx_queue=5\n");
            NBT_LOG("VIRTIO_FLOW_CONTROLLED_PORT_READY id=2 rx_queue=6 tx_queue=7\n");
            return 0;
        }
    }
    NBT_LOG("VIRTIO_CONTROL_EVENT_LIMIT\n");
    return -1;
}

/* ---------------------------------------------------------------- port 1 (queues 4/5) */
int nbt_port1_send(const void *p, uint32_t n)
{
    if (n > NBT_DATA_BUF) return -1;
    memcpy(g_p1_tx, p, n);
    vq_post(&g_q[5], g_p1_tx_phys, n, 0);
    return vq_wait(&g_q[5], (uint32_t *)0);
}

int nbt_port1_recv(void *dst, uint32_t cap, uint32_t *len)
{
    uint32_t l = 0;
    if (vq_wait(&g_q[4], &l) != 0) return -1;
    *len = l;
    memcpy(dst, g_p1_rx, l < cap ? l : cap);
    return 0;
}

void nbt_port1_repost(void) { vq_post(&g_q[4], g_p1_rx_phys, NBT_DATA_BUF, 1); }

/* ---------------------------------------------------------------- port 2 (queues 6/7) */
int nbt_port2_poll(const uint8_t **data, uint32_t *len, uint32_t *bad_id, uint32_t *bad_len)
{
    vring_q *q = &g_q[6];
    nbt_mb();
    if (q->used[1] == q->completed) return 0;
    volatile vused *e = &used_ring(q)[q->completed % q->n];
    uint32_t id = e->id, l = e->len;
    q->completed++;
    q->st_completed++;
    q->st_immediate++;
    if (id != 0 || l > NBT_DATA_BUF) { *bad_id = id; *bad_len = l; return -1; }
    *data = g_p2_rx;
    *len = l;
    return 1;
}

void nbt_port2_repost(void) { vq_post(&g_q[6], g_p2_rx_phys, NBT_DATA_BUF, 1); }
uint8_t *nbt_port2_txbuf(void) { return g_p2_tx; }

int nbt_port2_transmit(uint32_t n)
{
    vq_post(&g_q[7], g_p2_tx_phys, n, 0);
    return vq_wait(&g_q[7], (uint32_t *)0);
}

/* ---------------------------------------------------------------- perf markers */
void nbt_virtio_print_perf(uint32_t frame)
{
    for (uint32_t i = 0; i < 8; i++) {
        vring_q *q = &g_q[i];
        if (q->st_completed == 0 && q->st_timeouts == 0) continue;
        NBT_LOG("NBT_VFAST_PERF_QUEUE frame=%u queue=%u completed=%u immediate=%u spins=%llu sleeps=%llu max_spins=%u timeouts=%u\n",
                frame, i, q->st_completed, q->st_immediate, (unsigned long long)q->st_spins,
                (unsigned long long)q->st_sleeps, q->st_max, q->st_timeouts);
    }
}

void nbt_virtio_reset_if_found(void)
{
    if (g_io) io_out8(g_io + VREG_STATUS, 0);
}

/* ---------------------------------------------------------------- init sequence (section 2.4) */
int nbt_transport_init(void)
{
    /* 1. I/O privileges */
    if (ThreadCtl(QNX_NTO_TCTL_IO, (void *)0) == -1) return 1;

    /* 2. PCI scan, mechanism #1, bus 0 */
    uint32_t addr = 0;
    int found = 0;
    for (uint32_t slot = 0; slot < 32 && !found; slot++) {
        for (uint32_t fn = 0; fn < 8; fn++) {
            uint32_t a = 0x80000000u | (slot << 11) | (fn << 8);
            if (pci_read(a, 0) == 0x10031AF4u) { addr = a; found = 1; break; }
        }
    }
    if (!found) {
        NBT_LOG("VIRTIO_PCI_DEVICE_NOT_FOUND\n");
        return 2;
    }

    /* 3. BAR0 */
    uint32_t bar0 = pci_read(addr, 0x10);
    uint32_t cmd = pci_read(addr, 0x04);
    NBT_LOG("VIRTIO_PCI address=0x%x bar0=0x%x command=0x%x\n", addr, bar0, cmd);
    uint32_t base = bar0 & ~3u;
    if (!(bar0 & 1) || base == 0 || base >= 65536) return 3;

    /* 4. I/O space + bus master + INTx disabled; polling only */
    pci_write(addr, 0x04, (cmd & 0xFFFFu) | 0x405u);
    g_io = (uint16_t)base;

    /* 5. reset / ACK / DRIVER, features */
    io_out8(g_io + VREG_STATUS, 0);
    io_out8(g_io + VREG_STATUS, 1);
    io_out8(g_io + VREG_STATUS, 3);
    uint32_t host = io_in32(g_io + VREG_HOST_FEATURES);
    NBT_LOG("VIRTIO_FEATURES host=0x%x\n", host);
    if (!(host & 2u)) {
        NBT_LOG("VIRTIO_MULTIPORT_UNAVAILABLE\n");
        return 7;
    }
    io_out32(g_io + VREG_GUEST_FEATURES, 2u);

    /* 6. queues: 4,5 / 2,3 + control buffers / 6,7 + port 2 buffers / port 1 buffers */
    if (vq_setup(4) || vq_setup(5)) return 4;
    if (vq_setup(2) || vq_setup(3)) return 8;
    g_ctrl_rx = (uint8_t *)nbt_dma_alloc(4096, &g_ctrl_rx_phys);
    g_ctrl_tx = (uint8_t *)nbt_dma_alloc(4096, &g_ctrl_tx_phys);
    if (!g_ctrl_rx || !g_ctrl_tx) return 8;
    g_ctrl_slots = g_q[2].n < 16 ? g_q[2].n : 16;
    for (uint32_t s = 0; s < g_ctrl_slots; s++) ctrl_post_slot(s);
    if (vq_setup(6) || vq_setup(7)) return 10;
    g_p2_rx = (uint8_t *)nbt_dma_alloc(NBT_DATA_BUF, &g_p2_rx_phys);
    g_p2_tx = (uint8_t *)nbt_dma_alloc(NBT_DATA_BUF, &g_p2_tx_phys);
    if (!g_p2_rx || !g_p2_tx) return 10;
    vq_post_ex(&g_q[6], g_p2_rx_phys, NBT_DATA_BUF, 1, 0);
    g_p1_rx = (uint8_t *)nbt_dma_alloc(NBT_DATA_BUF, &g_p1_rx_phys);
    g_p1_tx = (uint8_t *)nbt_dma_alloc(NBT_DATA_BUF, &g_p1_tx_phys);
    if (!g_p1_rx || !g_p1_tx) return 5;
    vq_post_ex(&g_q[4], g_p1_rx_phys, NBT_DATA_BUF, 1, 0);

    /* 7. DRIVER_OK, kick the receive queues */
    io_out8(g_io + VREG_STATUS, 7);
    vq_notify(&g_q[4]);
    vq_notify(&g_q[6]);

    /* 8. control handshake */
    if (control_handshake() != 0) return 9;

    /* 9. MTP worker */
    if (nbt_input_start() != 0) return 11;

    /* 10. DMA bootstrap */
    if (nbt_dma_bootstrap() != 0) return 12;

    /* 11. final status */
    uint32_t st = io_in8(g_io + VREG_STATUS);
    NBT_LOG("VIRTIO_DRIVER_READY status=%u vfast_io=0x%x\n", st, (unsigned)g_io);
    return st == 7 ? 0 : 6;
}
