/* © 2026 davisod & JEtsKi
 * libnbtgl (bridge v2, guest): shared declarations - QNX imports, CPU primitives, module APIs.
 */
#ifndef NBT_GUEST_H
#define NBT_GUEST_H

#include <stdint.h>
#include <stddef.h>
#include <stdarg.h>

#define NBT_API    __attribute__((visibility("default")))
#define NBT_IMPORT __attribute__((visibility("default")))

/* ------------------------------------------------------------------------- */
/* QNX 6.5 libc / libsocket imports (all cdecl, resolved from HmiMain3D).     */
/* Only names from the allowed import list of the spec (section 2.1).         */
/* ------------------------------------------------------------------------- */
typedef int qnx_pthread_t;
typedef int qnx_pthread_key_t;

NBT_IMPORT int atoi(const char *s);
NBT_IMPORT int usleep(unsigned int usec);
NBT_IMPORT int mem_offset64(const void *addr, int fd, size_t len, int64_t *off, size_t *contig);
NBT_IMPORT void abort(void) __attribute__((noreturn));
NBT_IMPORT void *pthread_getspecific(qnx_pthread_key_t key);
NBT_IMPORT int pthread_setspecific(qnx_pthread_key_t key, const void *value);
NBT_IMPORT int pthread_key_create(qnx_pthread_key_t *key, void (*dtor)(void *));
NBT_IMPORT qnx_pthread_t pthread_self(void);
NBT_IMPORT int pthread_create(qnx_pthread_t *thr, const void *attr, void *(*fn)(void *), void *arg);
NBT_IMPORT int pthread_join(qnx_pthread_t thr, void **ret);
NBT_IMPORT int send(int fd, const void *buf, size_t n, int flags);
NBT_IMPORT int getpid(void);
NBT_IMPORT int read(int fd, void *buf, size_t n);
NBT_IMPORT int write(int fd, const void *buf, size_t n);
NBT_IMPORT int close(int fd);
NBT_IMPORT int fflush(void *stream);
NBT_IMPORT int socket(int domain, int type, int proto);
NBT_IMPORT int connect(int fd, const void *addr, unsigned int len);
NBT_IMPORT int setsockopt(int fd, int level, int name, const void *val, unsigned int len);
NBT_IMPORT int select(int nfds, void *rd, void *wr, void *ex, void *timeout);
NBT_IMPORT int strcmp(const char *a, const char *b);
NBT_IMPORT size_t strlen(const char *s);
NBT_IMPORT int *__get_errno_ptr(void);
NBT_IMPORT void *malloc(size_t n);
NBT_IMPORT void *realloc(void *p, size_t n);
NBT_IMPORT void free(void *p);
NBT_IMPORT int printf(const char *fmt, ...);
NBT_IMPORT int vsnprintf(char *buf, size_t n, const char *fmt, va_list ap);
NBT_IMPORT void *mmap64(void *addr, size_t len, int prot, int flags, int fd, int64_t off);
NBT_IMPORT int ClockTime(int id, const uint64_t *newval, uint64_t *oldval);
NBT_IMPORT char *getenv(const char *name);
NBT_IMPORT int ThreadCtl(int cmd, void *data);

/* QNX constants (public API values quoted by the spec). */
#define QNX_NTO_TCTL_IO       1
#define QNX_CLOCK_REALTIME    0
#define QNX_CLOCK_MONOTONIC   2
#define QNX_PROT_RW           0x300
#define QNX_MAP_PHYS_ANON     0x90001
#define QNX_NOFD              (-1)
#define QNX_MSG_NOWAIT_NOSIG  0x880

/* Every serial diagnostic is a printf line followed by fflush. */
#define NBT_LOG(...) do { printf(__VA_ARGS__); fflush((void *)0); } while (0)

/* ------------------------------------------------------------------------- */
/* CPU primitives                                                             */
/* ------------------------------------------------------------------------- */
static inline void nbt_mb(void) { __asm__ __volatile__("lock; addl $0,(%%esp)" ::: "memory"); }
static inline void nbt_pause(void) { __asm__ __volatile__("pause" ::: "memory"); }
static inline void io_out8(uint16_t p, uint8_t v) { __asm__ __volatile__("outb %0,%1" :: "a"(v), "Nd"(p)); }
static inline void io_out16(uint16_t p, uint16_t v) { __asm__ __volatile__("outw %0,%1" :: "a"(v), "Nd"(p)); }
static inline void io_out32(uint16_t p, uint32_t v) { __asm__ __volatile__("outl %0,%1" :: "a"(v), "Nd"(p)); }
static inline uint8_t io_in8(uint16_t p) { uint8_t v; __asm__ __volatile__("inb %1,%0" : "=a"(v) : "Nd"(p)); return v; }
static inline uint16_t io_in16(uint16_t p) { uint16_t v; __asm__ __volatile__("inw %1,%0" : "=a"(v) : "Nd"(p)); return v; }
static inline uint32_t io_in32(uint16_t p) { uint32_t v; __asm__ __volatile__("inl %1,%0" : "=a"(v) : "Nd"(p)); return v; }

static inline int nbt_errno(void) { return *__get_errno_ptr(); }

/* rt.c */
void *memcpy(void *d, const void *s, size_t n);
void *memset(void *d, int c, size_t n);
void *memmove(void *d, const void *s, size_t n);
int memcmp(const void *a, const void *b, size_t n);
void nbt_fd2(const char *s);                       /* write whole string to fd 2 */
void nbt_fd2n(const void *p, size_t n);
uint64_t nbt_monotonic_ns(void);                   /* 0 on failure */

/* ------------------------------------------------------------------------- */
/* virtio.c - legacy virtio-console driver (polling only)                     */
/* ------------------------------------------------------------------------- */
#define NBT_DATA_BUF 65536u

int  nbt_transport_init(void);                      /* 0 or failure code 2..12 */
void nbt_virtio_reset_if_found(void);
void *nbt_dma_alloc(uint32_t bytes, uint32_t *phys); /* zeroed, contiguous, <4 GiB */
/* port 1 (queues 4/5) */
int  nbt_port1_send(const void *p, uint32_t n);
int  nbt_port1_recv(void *dst, uint32_t cap, uint32_t *len);
void nbt_port1_repost(void);
/* port 2 (queues 6/7) */
int  nbt_port2_poll(const uint8_t **data, uint32_t *len, uint32_t *bad_id, uint32_t *bad_len); /* 1 got, 0 none, -1 invalid */
void nbt_port2_repost(void);
uint8_t *nbt_port2_txbuf(void);
int  nbt_port2_transmit(uint32_t n);
void nbt_virtio_print_perf(uint32_t frame);

/* dma.c - shared ring region */
int  nbt_dma_bootstrap(void);                       /* 0 ok */
int  nbt_dma_send(const void *p, uint32_t n);       /* 0 ok, -1 fail */
int  nbt_dma_recv(void *p, uint32_t n);             /* 0 ok, -1 fail */

/* input.c - MTP worker and port 2 framer */
int  nbt_input_start(void);                         /* 0 ok */
void nbt_input_stop(void);
int  nbt_input_send_ack(const uint8_t pkt[8], uint32_t key); /* used by keyboard HAL */

/* keyboard.c */
int  nbt_keyboard_packet(const uint8_t *pkt, uint32_t len); /* 0 ok, -1 failure */
#ifdef NBT_EXPERIMENTAL_NATIVE
int nbt_native_writable_page(uintptr_t address);
int nbt_sports_init(void);
int nbt_sports_update(unsigned channel0_percent, unsigned channel1_percent);
void nbt_sports_tick(void);
int nbt_native_devices_install(void);
uint32_t nbt_native_devices_take_selection(void);
void nbt_native_devices_request_selection(uint32_t identifier);
#ifdef NBT_STANDALONE_NATIVE
void nbt_native_mailbox_selection(uint32_t identifier);
#endif
#endif

/* ------------------------------------------------------------------------- */
/* link.c - per-thread state, lock, batching, record building                 */
/* ------------------------------------------------------------------------- */
#define NBT_MAX_ATTR 16
#define NBT_MAX_PAYLOAD (16u * 1024u * 1024u)

typedef struct nbt_attr {
    uint32_t enabled, size, type, norm, stride, buffer;
    const void *ptr;
} nbt_attr;

typedef struct nbt_thread {
    uint8_t *rec;            /* record under construction (20-byte prefix + payload) */
    uint32_t rec_cap, rec_len, rec_end, rec_op;
    uint32_t array_buf, element_buf;
    nbt_attr attr[NBT_MAX_ATTR];
    int io_ready;
} nbt_thread;

nbt_thread *nbt_self(void);
uint32_t nbt_new_name(void);
void nbt_rec_begin(nbt_thread *t, uint32_t op, uint32_t len);
void nbt_rec_u32(nbt_thread *t, uint32_t v);
void nbt_rec_i32(nbt_thread *t, int32_t v);
void nbt_rec_f32(nbt_thread *t, float v);
void nbt_rec_bytes(nbt_thread *t, const void *p, uint32_t n);
void nbt_rec_send(nbt_thread *t);                                   /* asynchronous record */
int  nbt_rec_call(nbt_thread *t, void *r1, uint32_t n1, void *r2, uint32_t n2); /* sync; 1 ok */
void nbt_flush_if_ready(void);
void nbt_send_simple(uint32_t op, int n, ...);                       /* n u32 fields */

/* gles.c (used by EGL side) */
void nbt_gl_finish_internal(void);

#endif
