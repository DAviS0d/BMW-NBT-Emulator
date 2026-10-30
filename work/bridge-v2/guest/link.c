/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): per-thread state, global lock, 64 KiB batch, record framing, lazy init, _fini.
 */
#include "nbt_guest.h"

#define BATCH_BYTES 65536u
#define PREFIX_BYTES 20u

/* ---------------------------------------------------------------- per-thread state */
static volatile int g_key_state;          /* 0 none, 1 creating, 2 ready */
static qnx_pthread_key_t g_key;

static void thread_state_free(void *p)
{
    nbt_thread *t = (nbt_thread *)p;
    if (!t) return;
    free(t->rec);
    free(t);
}

nbt_thread *nbt_self(void)
{
    if (g_key_state != 2) {
        if (__sync_bool_compare_and_swap(&g_key_state, 0, 1)) {
            if (pthread_key_create(&g_key, thread_state_free) != 0) abort();
            nbt_mb();
            g_key_state = 2;
        } else {
            while (g_key_state != 2) usleep(1000);
        }
    }
    nbt_thread *t = (nbt_thread *)pthread_getspecific(g_key);
    if (!t) {
        t = (nbt_thread *)malloc(sizeof *t);
        if (!t) abort();
        memset(t, 0, sizeof *t);
        if (pthread_setspecific(g_key, t) != 0) abort();
    }
    return t;
}

static volatile uint32_t g_name_counter;
uint32_t nbt_new_name(void) { return __sync_add_and_fetch(&g_name_counter, 1u); }

/* ---------------------------------------------------------------- lock + batch */
static volatile int g_lock;
static uint8_t g_batch[BATCH_BYTES];
static uint32_t g_batch_len;
static volatile int g_transport_state;    /* 0 none, 1 initialising, 2 ready */

static void lock_take(void)
{
    while (__sync_lock_test_and_set(&g_lock, 1) != 0) usleep(1000);
}

static int lock_try(void) { return __sync_lock_test_and_set(&g_lock, 1) == 0; }
static void lock_drop(void) { __sync_lock_release(&g_lock); }

static void batch_flush_locked(void)
{
    if (g_batch_len == 0) return;
    if (nbt_dma_send(g_batch, g_batch_len) != 0) abort();
    g_batch_len = 0;
}

static void submit_locked(const uint8_t *r, uint32_t n, uint32_t op, int sync)
{
    if (n > BATCH_BYTES) {
        batch_flush_locked();
        if (nbt_dma_send(r, n) != 0) abort();
        return;
    }
    if (n > BATCH_BYTES - g_batch_len) batch_flush_locked();
    memcpy(g_batch + g_batch_len, r, n);
    g_batch_len += n;
    if (sync || op == 5 || op == 6 || g_batch_len == BATCH_BYTES) batch_flush_locked();
}

static void ensure_transport(nbt_thread *t)
{
    if (!t->io_ready) {
        if (ThreadCtl(QNX_NTO_TCTL_IO, (void *)0) == -1) {
            nbt_fd2n("glbridge: virtio I/O privilege failed", 37);
            abort();
        }
        t->io_ready = 1;
    }
    if (g_transport_state == 2) return;
    if (__sync_bool_compare_and_swap(&g_transport_state, 0, 1)) {
        int code = nbt_transport_init();
        if (code != 0) {
            NBT_LOG("glbridge: virtio init failed code=%d\n", code);
            abort();
        }
        nbt_mb();
        g_transport_state = 2;
    } else {
        while (g_transport_state != 2) usleep(1000);
    }
}

void nbt_flush_if_ready(void)
{
    if (g_transport_state != 2) return;
    lock_take();
    batch_flush_locked();
    lock_drop();
}

/* ---------------------------------------------------------------- record builder */
static void put_raw(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }

void nbt_rec_begin(nbt_thread *t, uint32_t op, uint32_t len)
{
    if (len > NBT_MAX_PAYLOAD) abort();
    uint32_t need = PREFIX_BYTES + len;
    if (need > t->rec_cap) {
        uint32_t cap = t->rec_cap ? t->rec_cap : 256;
        while (cap < need) cap = cap * 2 > cap ? cap * 2 : need;
        uint8_t *nb = (uint8_t *)realloc(t->rec, cap);
        if (!nb) abort();
        t->rec = nb;
        t->rec_cap = cap;
    }
    put_raw(t->rec + 0, 119u);
    put_raw(t->rec + 4, 4u);
    put_raw(t->rec + 8, (uint32_t)getpid());
    put_raw(t->rec + 12, op);
    put_raw(t->rec + 16, len);
    t->rec_len = PREFIX_BYTES;
    t->rec_end = need;
    t->rec_op = op;
}

void nbt_rec_bytes(nbt_thread *t, const void *p, uint32_t n)
{
    if (n > t->rec_end - t->rec_len) abort();
    memcpy(t->rec + t->rec_len, p, n);
    t->rec_len += n;
}

void nbt_rec_u32(nbt_thread *t, uint32_t v) { nbt_rec_bytes(t, &v, 4); }
void nbt_rec_i32(nbt_thread *t, int32_t v) { nbt_rec_bytes(t, &v, 4); }
void nbt_rec_f32(nbt_thread *t, float v) { nbt_rec_bytes(t, &v, 4); }

void nbt_rec_send(nbt_thread *t)
{
    if (t->rec_len != t->rec_end) abort();
    ensure_transport(t);
    lock_take();
    submit_locked(t->rec, t->rec_len, t->rec_op, 0);
    lock_drop();
}

/* Synchronous record: the lock stays held until the whole reply has been consumed. */
int nbt_rec_call(nbt_thread *t, void *r1, uint32_t n1, void *r2, uint32_t n2)
{
    if (t->rec_len != t->rec_end) abort();
    ensure_transport(t);
    lock_take();
    submit_locked(t->rec, t->rec_len, t->rec_op, 1);
    int ok = nbt_dma_recv(r1, n1) == 0;
    if (ok && n2) ok = nbt_dma_recv(r2, n2) == 0;
    lock_drop();
    return ok;
}

void nbt_send_simple(uint32_t op, int n, ...)
{
    nbt_thread *t = nbt_self();
    va_list ap;
    va_start(ap, n);
    nbt_rec_begin(t, op, (uint32_t)n * 4u);
    for (int i = 0; i < n; i++) nbt_rec_u32(t, va_arg(ap, uint32_t));
    va_end(ap);
    nbt_rec_send(t);
}

/* ---------------------------------------------------------------- unload */
NBT_API void _fini(void)
{
    nbt_input_stop();
    if (g_transport_state == 2) {
        if (lock_try()) {
            /* at unload a failed flush (host gone) must not abort the exiting process */
            if (g_batch_len) (void)nbt_dma_send(g_batch, g_batch_len);
            g_batch_len = 0;
            lock_drop();
        } else {
            nbt_fd2("NBT_BATCH_FINI_SKIPPED_BUSY\n");
        }
    }
    nbt_virtio_reset_if_found();
}
