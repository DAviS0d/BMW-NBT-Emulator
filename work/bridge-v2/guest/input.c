/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): MTP worker thread (virtio port 2 <-> TCP 127.0.0.1:50123) and port 2 framer.
 */
#include "nbt_guest.h"

#define FRAME_MAX 4096u

static qnx_pthread_t g_thread;
static volatile int g_started;
static volatile int g_stop;
static int g_fd = -1;
static uint64_t g_to_native;    /* bytes received from the host on port 2 (counted when the chunk arrives) */
static uint64_t g_to_host;      /* bytes sent to the host on queue 7 */

/* framer state */
static uint8_t g_frame[FRAME_MAX];
static uint32_t g_have, g_need;

static void diag(const char *ev, int value, int err)
{
    NBT_LOG("NBT_MTP_VIRTIO_%s value=%d errno=%d host_to_native=%llu native_to_host=%llu\n",
            ev, value, err, (unsigned long long)g_to_native, (unsigned long long)g_to_host);
}

static int chunk_should_log(uint32_t count)
{
    return count <= 8 || (count & (count - 1)) == 0;
}

/* ---------------------------------------------------------------- TCP side */
static int tcp_send_all(const uint8_t *p, uint32_t n)
{
    uint32_t sent = 0;
    int retries = 0, reported = 0;
    while (sent < n) {
        int r = send(g_fd, p + sent, n - sent, QNX_MSG_NOWAIT_NOSIG);
        if (r > 0) {
            sent += (uint32_t)r;
            continue;
        }
        if (r == 0 || ++retries > 2000) {
            diag("TCP_SEND_FAILED", (int)sent, r == 0 ? 0 : nbt_errno());
            return -1;
        }
        if (!reported) { reported = 1; diag("TCP_SEND_RETRY", (int)sent, nbt_errno()); }
        usleep(1000);
    }
    return 0;
}

int nbt_input_send_ack(const uint8_t pkt[8], uint32_t key)
{
    uint8_t *tx = nbt_port2_txbuf();
    memcpy(tx, pkt, 8);
    if (nbt_port2_transmit(8) != 0) {
        NBT_LOG("NBT_KEYBOARD_ACK_TX_FAILED key=%u\n", key);
        return -1;
    }
    g_to_host += 8;
    return 0;
}

/* ---------------------------------------------------------------- framer (section 3.2) */
static int frame_complete(void)
{
    uint32_t len = g_need;
    if (g_frame[2] == 0xFE) return nbt_keyboard_packet(g_frame, len);
    if (g_frame[2] == 0x02 && len < 12) {
        NBT_LOG("NBT_PORT2_MTP_HEADER_REJECTED length=%u\n", len);
        return -1;
    }
    return tcp_send_all(g_frame, len);
}

static int framer_feed(const uint8_t *p, uint32_t n)
{
    while (n > 0) {
        if (g_have < 2) {
            g_frame[g_have++] = *p++;
            n--;
            if (g_have == 2) {
                uint32_t len = ((uint32_t)g_frame[0] << 8) | g_frame[1];
                if (len < 7 || len > FRAME_MAX) {
                    NBT_LOG("NBT_PORT2_FRAME_LENGTH_REJECTED length=%u\n", len);
                    g_have = 0;
                    return -1;
                }
                g_need = len;
            }
            continue;
        }
        uint32_t take = g_need - g_have;
        if (take > n) take = n;
        memcpy(g_frame + g_have, p, take);
        g_have += take;
        p += take;
        n -= take;
        if (g_have == g_need) {
            g_have = 0;
            if (frame_complete() != 0) return -1;
        }
    }
    return 0;
}

/* ---------------------------------------------------------------- worker */
typedef struct qnx_sockaddr_in {
    uint8_t len, family;
    uint16_t port;
    uint32_t addr;
    uint8_t zero[8];
} qnx_sockaddr_in;

static int connect_mtp2most(void)
{
    qnx_sockaddr_in sa;
    memset(&sa, 0, sizeof sa);
    sa.len = sizeof sa;
    sa.family = 2;                         /* AF_INET */
    sa.port = (uint16_t)((50123 >> 8) | ((50123 & 0xFF) << 8));
    sa.addr = 0x0100007Fu;                 /* 127.0.0.1, network order */
    for (int attempt = 1; attempt <= 300; attempt++) {
        if (g_stop) return -1;
        int fd = socket(2, 1, 0);
        int err;
        if (fd >= 0) {
            if (connect(fd, &sa, sizeof sa) == 0) return fd;
            err = nbt_errno();
            close(fd);
        } else {
            err = nbt_errno();
        }
        if (attempt == 1 || attempt % 25 == 0) diag("CONNECT_RETRY", attempt, err);
        if (attempt < 300) usleep(100000);
    }
    diag("CONNECT_FAILED", 300, nbt_errno());
    return -1;
}

static void *worker(void *arg)
{
    (void)arg;
    uint32_t rx_chunks = 0, tx_chunks = 0, read_fail = 0, select_fail = 0;
    uint8_t rdset[128];

    if (ThreadCtl(QNX_NTO_TCTL_IO, (void *)0) == -1) {
        diag("IO_PRIVILEGE_FAILED", 0, nbt_errno());
        goto out;
    }
    g_fd = connect_mtp2most();
    if (g_fd < 0) goto out;
    {
        int one = 1;
        int r = setsockopt(g_fd, 6, 1, &one, sizeof one);
        NBT_LOG("NBT_MTP_VIRTIO_TCP_NODELAY fd=%d result=%d errno=%d value=1\n", g_fd, r, r == 0 ? 0 : nbt_errno());
    }
    diag("CONNECTED_127_0_0_1_50123", g_fd, 0);
    if (g_fd >= 1024) {
        diag("FD_OUTSIDE_SELECT_SET", g_fd, 0);
        goto out;
    }
    diag("BIDIRECTIONAL_READY_PORT2_50123", 2, 0);

    for (uint32_t iter = 1; !g_stop; iter++) {
        int progress = 0;

        /* host -> native */
        const uint8_t *data;
        uint32_t len, bad_id, bad_len;
        int got = nbt_port2_poll(&data, &len, &bad_id, &bad_len);
        if (got < 0) {
            diag("RX_DESCRIPTOR_INVALID", (int)bad_id, (int)bad_len);
            goto out;
        }
        if (got > 0) {
            progress = 1;
            rx_chunks++;
            g_to_native += len;      /* cumulative, including this chunk */
            if (chunk_should_log(rx_chunks)) diag("HOST_TO_NATIVE_CHUNK", (int)len, 0);
            if (framer_feed(data, len) != 0) goto out;
            nbt_port2_repost();
        }

        /* native -> host */
        memset(rdset, 0, sizeof rdset);
        rdset[g_fd >> 3] |= (uint8_t)(1u << (g_fd & 7));
        uint32_t tv[2] = { 0, 0 };
        int s = select(g_fd + 1, rdset, (void *)0, (void *)0, tv);
        if (s < 0) {
            select_fail++;
            if (select_fail == 1) diag("SELECT_RETRY", s, nbt_errno());
            if (select_fail > 1000) { diag("SELECT_FAILED", s, nbt_errno()); goto out; }
        } else {
            select_fail = 0;
            if (s > 0 && (rdset[g_fd >> 3] & (1u << (g_fd & 7)))) {
                uint8_t *tx = nbt_port2_txbuf();
                int r = read(g_fd, tx, NBT_DATA_BUF);
                if (r == 0) { diag("NATIVE_EOF", 0, 0); goto out; }
                if (r < 0) {
                    read_fail++;
                    if (read_fail == 1) diag("READ_RETRY", r, nbt_errno());
                    if (read_fail > 1000) { diag("READ_FAILED", r, nbt_errno()); goto out; }
                } else {
                    read_fail = 0;
                    if (nbt_port2_transmit((uint32_t)r) != 0) { diag("TX_COMPLETION_FAILED", r, 0); goto out; }
                    g_to_host += (uint32_t)r;
                    tx_chunks++;
                    progress = 1;
                    if (chunk_should_log(tx_chunks)) diag("NATIVE_TO_HOST_CHUNK", r, 0);
                }
            }
        }
        if (!progress || iter % 64 == 0) usleep(1000);
    }
out:
    if (g_fd >= 0) { close(g_fd); g_fd = -1; }
    diag("WORKER_STOPPED", g_stop ? 1 : 0, 0);
    return (void *)0;
}

int nbt_input_start(void)
{
    g_stop = 0;
    int rc = pthread_create(&g_thread, (const void *)0, worker, (void *)0);
    if (rc != 0) {
        diag("THREAD_FAILED", rc, rc);
        return -1;
    }
    g_started = 1;
    NBT_LOG("NBT_MTP_VIRTIO_WORKER_CREATED value=%d errno=0 host_to_native=0 native_to_host=0\n", (int)g_thread);
    return 0;
}

void nbt_input_stop(void)
{
    if (!g_started) return;
    g_stop = 1;
    pthread_join(g_thread, (void **)0);
    g_started = 0;
}
