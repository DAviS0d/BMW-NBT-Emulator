/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): shared declarations of the Windows renderer modules.
 */
#ifndef GLH_H
#define GLH_H

#include <winsock2.h>
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* error codes used by the transport layer (independent of the CRT errno table) */
enum {
    GLH_OK = 0, GLH_EPERM = 1, GLH_EINTR = 4, GLH_EIO = 5, GLH_EAGAIN = 11, GLH_EINVAL = 22,
    GLH_EPIPE = 32, GLH_ECONNRESET = 104, GLH_EPROTO = 71
};

/* logx.c - stderr line logging (one write + flush per line) */
void glh_log(const char *fmt, ...);
void glh_log_init(void);

/* idle.c - wait policy of section 5.12 */
typedef struct glh_idle {
    LARGE_INTEGER last_activity;
    HANDLE timer;
    int timer_tried;
} glh_idle;
void glh_idle_init(glh_idle *w);
void glh_idle_touch(glh_idle *w);
void glh_idle_wait(glh_idle *w);
void glh_idle_close(glh_idle *w);

/* dmaring.c - cross-process DMA region access and ring protocol */
#define DMA_REGION_BYTES 135168u
#define DMA_RING_CAP     65536u
#define DMA_OFF_ATTACHED 64u
#define DMA_OFF_STOP     68u
#define DMA_OFF_TX_HEAD  128u
#define DMA_OFF_TX_TAIL  192u
#define DMA_OFF_RX_HEAD  256u
#define DMA_OFF_RX_TAIL  320u
#define DMA_OFF_TX_RING  4096u
#define DMA_OFF_RX_RING  69632u

typedef struct glh_dma {
    HANDLE process;
    uint8_t *remote;            /* region base address inside the target process */
    int own_handle;
    uint32_t pid;
    uint32_t phys;
    uint32_t tx_tail;           /* host-owned cursors */
    uint32_t rx_head;
    uint8_t *cache;             /* bulk-read copy of consumed TX bytes */
    uint32_t cache_pos, cache_len;
    uint64_t bytes_read, bytes_written;
    volatile LONG *cancel;
    int last_error;
    glh_idle idle;
} glh_dma;

int  glh_dma_mem_read(glh_dma *d, uint32_t off, void *dst, uint32_t n);         /* 0 or -GLH_E* */
int  glh_dma_mem_write(glh_dma *d, uint32_t off, const void *src, uint32_t n);  /* 0 or -GLH_E* */
int  glh_dma_open_local(glh_dma *d, uint8_t *region, volatile LONG *cancel);     /* test helper: own process */
int  glh_dma_attach(glh_dma *d, const uint8_t payload[28], const char *config_path, volatile LONG *cancel);
long long glh_dma_read(glh_dma *d, void *dst, size_t n);        /* >=0 delivered (0 = EOF), -1 error */
long long glh_dma_write(glh_dma *d, const void *src, size_t n); /* written, -1 error */
void glh_dma_signal_stop(glh_dma *d);
void glh_dma_close(glh_dma *d);

/* channel.c - record transport: stdio, socket, then DMA after op 144 */
typedef struct glh_channel glh_channel;
int  glh_channel_open(glh_channel **out);               /* returns exit code on failure (2), 0 ok */
int  glh_channel_read_exact(glh_channel *c, void *dst, size_t n); /* 1 ok, 0 EOF/error */
int  glh_channel_write(glh_channel *c, const void *src, size_t n);/* 0 ok, -1 failure */
int  glh_channel_write_base(glh_channel *c, const void *src, size_t n); /* socket/stdout, never DMA */
int  glh_channel_is_socket(glh_channel *c);
volatile LONG *glh_channel_cancel_flag(glh_channel *c);
void glh_channel_use_dma(glh_channel *c, glh_dma *d);
glh_dma *glh_channel_dma(glh_channel *c);
void glh_channel_shutdown(glh_channel *c);              /* section 5.2 step 7 */

/* validate.c */
uint32_t glh_normalize_op(uint32_t op, uint32_t len);   /* 128/len 12 -> 138 */
int glh_validate(uint32_t op, const uint8_t *p, uint32_t len); /* 1 valid */

/* publish.c - PPM publication with a single off-thread worker */
void glh_publish_init(void);
void glh_publish_async(uint8_t **pixels, int w, int h, const char *path); /* may swap *pixels */
int  glh_publish_sync(const uint8_t *pixels, int w, int h, const char *path);
void glh_publish_shutdown(void);

/* shaders.c */
uint64_t glh_fnv1a64(const uint8_t *p, size_t n);
int glh_shader_cache_lookup(const char *dir, uint64_t hash, uint32_t length, int *blend, char **glsl); /* 1 found */

/* render.c */
int glh_render_session(glh_channel *ch); /* returns process exit code */
void glh_render_release_dma(void);

static inline uint32_t rd_u32(const uint8_t *p) { uint32_t v; memcpy(&v, p, 4); return v; }
static inline int32_t rd_i32(const uint8_t *p) { int32_t v; memcpy(&v, p, 4); return v; }
static inline float rd_f32(const uint8_t *p) { float v; memcpy(&v, p, 4); return v; }

#endif
