/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): DMA region attach/validation, guarded cross-process access, bulk ring I/O.
 */
#include "glh.h"
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

typedef LONG (NTAPI *nt_write_vm_fn)(HANDLE, PVOID, PVOID, SIZE_T, PSIZE_T);
typedef ULONG (NTAPI *rtl_status_fn)(LONG);

static nt_write_vm_fn g_nt_write;
static rtl_status_fn g_nt_status_to_dos;
static volatile LONG g_nt_resolved;

static void resolve_ntdll(void)
{
    if (InterlockedCompareExchange(&g_nt_resolved, 1, 0) != 0) return;
    HMODULE nt = GetModuleHandleW(L"ntdll.dll");
    if (nt) {
        g_nt_write = (nt_write_vm_fn)(void *)GetProcAddress(nt, "NtWriteVirtualMemory");
        g_nt_status_to_dos = (rtl_status_fn)(void *)GetProcAddress(nt, "RtlNtStatusToDosError");
    }
}

/* ------------------------------------------------------------------ guarded memory access (section 5.4) */
static int write_allowed(uint32_t off, uint32_t n)
{
    if (n == 4 && (off == 64 || off == 68 || off == 192 || off == 196 || off == 256 || off == 260)) return 1;
    return off >= DMA_OFF_RX_RING && (uint64_t)off + n <= DMA_REGION_BYTES;
}

int glh_dma_mem_read(glh_dma *d, uint32_t off, void *dst, uint32_t n)
{
    if ((uint64_t)off + n > DMA_REGION_BYTES || off >= DMA_REGION_BYTES) return -GLH_EINVAL;
    if (n == 0) return 0;
    SIZE_T done = 0;
    if (!ReadProcessMemory(d->process, d->remote + off, dst, n, &done) || done != n) {
        glh_log("GLHOST_DMA_MEMORY_ERROR write=0 offset=%u count=%u done=%llu winerror=%lu",
                off, n, (unsigned long long)done, (unsigned long)GetLastError());
        return -GLH_EIO;
    }
    return 0;
}

int glh_dma_mem_write(glh_dma *d, uint32_t off, const void *src, uint32_t n)
{
    if ((uint64_t)off + n > DMA_REGION_BYTES || off >= DMA_REGION_BYTES) return -GLH_EINVAL;
    if (!write_allowed(off, n)) return -GLH_EPERM;
    if (n == 0) return 0;
    SIZE_T done = 0;
    unsigned long err = 0;
    int ok;
    if (g_nt_write) {
        LONG st = g_nt_write(d->process, d->remote + off, (PVOID)src, n, &done);
        ok = st >= 0 && done == n;
        if (!ok) err = g_nt_status_to_dos ? g_nt_status_to_dos(st) : (unsigned long)st;
    } else {
        ok = WriteProcessMemory(d->process, d->remote + off, src, n, &done) && done == n;
        if (!ok) err = GetLastError();
    }
    if (!ok) {
        glh_log("GLHOST_DMA_MEMORY_ERROR write=1 offset=%u count=%u done=%llu winerror=%lu",
                off, n, (unsigned long long)done, err);
        return -GLH_EIO;
    }
    return 0;
}

/* value, complement, value again: 1 valid, 0 in-flight, <0 memory error */
static int read_cursor(glh_dma *d, uint32_t off, uint32_t *out)
{
    uint32_t vc[2], again;
    int rc = glh_dma_mem_read(d, off, vc, 8);
    if (rc) return rc;
    rc = glh_dma_mem_read(d, off, &again, 4);
    if (rc) return rc;
    if (vc[0] != again || vc[1] != ~vc[0]) return 0;
    *out = vc[0];
    return 1;
}

static int publish_cursor(glh_dma *d, uint32_t off, uint32_t v)
{
    uint32_t c = ~v;
    int rc = glh_dma_mem_write(d, off, &v, 4);
    if (rc) return rc;
    MemoryBarrier();
    rc = glh_dma_mem_write(d, off + 4, &c, 4);
    MemoryBarrier();
    return rc;
}

static int cancelled(glh_dma *d) { return d->cancel && *d->cancel != 0; }

static int alloc_cache(glh_dma *d)
{
    d->cache = (uint8_t *)malloc(DMA_RING_CAP);
    d->cache_pos = d->cache_len = 0;
    return d->cache != NULL;
}

static int adopt_cursors(glh_dma *d)
{
    for (int tries = 0; tries < 1000000; tries++) {
        uint32_t t, h;
        int a = read_cursor(d, DMA_OFF_TX_TAIL, &t);
        int b = read_cursor(d, DMA_OFF_RX_HEAD, &h);
        if (a < 0 || b < 0) return -1;
        if (a == 1 && b == 1) { d->tx_tail = t; d->rx_head = h; return 0; }
        YieldProcessor();
    }
    return -1;
}

int glh_dma_open_local(glh_dma *d, uint8_t *region, volatile LONG *cancel)
{
    memset(d, 0, sizeof *d);
    resolve_ntdll();
    d->process = GetCurrentProcess();
    d->remote = region;
    d->cancel = cancel;
    d->pid = GetCurrentProcessId();
    glh_idle_init(&d->idle);
    if (!alloc_cache(d)) return -1;
    return adopt_cursors(d);
}

/* ------------------------------------------------------------------ ring reads (TX: guest -> host), bulk */
long long glh_dma_read(glh_dma *d, void *dst, size_t n)
{
    uint8_t *out = (uint8_t *)dst;
    size_t delivered = 0;
    while (delivered < n) {
        if (d->cache_pos < d->cache_len) {
            size_t take = d->cache_len - d->cache_pos;
            if (take > n - delivered) take = n - delivered;
            memcpy(out + delivered, d->cache + d->cache_pos, take);
            d->cache_pos += (uint32_t)take;
            delivered += take;
            continue;
        }
        if (cancelled(d)) return (long long)delivered;
        uint32_t head;
        int rc = read_cursor(d, DMA_OFF_TX_HEAD, &head);
        if (rc < 0) { d->last_error = GLH_EIO; return delivered ? (long long)delivered : -1; }
        if (rc == 0) { glh_idle_wait(&d->idle); continue; }
        uint32_t avail = head - d->tx_tail;
        if (avail > DMA_RING_CAP) {
            glh_log("GLHOST_DMA_BAD_TX head=%u tail=%u", head, d->tx_tail);
            d->last_error = GLH_EPROTO;
            return -1;
        }
        if (avail == 0) {
            if (delivered) return (long long)delivered;
            glh_idle_wait(&d->idle);
            continue;
        }
        uint32_t pos = d->tx_tail % DMA_RING_CAP;
        uint32_t chunk = DMA_RING_CAP - pos;
        if (chunk > avail) chunk = avail;
        rc = glh_dma_mem_read(d, DMA_OFF_TX_RING + pos, d->cache, chunk);
        if (rc) { d->last_error = GLH_EIO; return delivered ? (long long)delivered : -1; }
        d->tx_tail += chunk;
        if (publish_cursor(d, DMA_OFF_TX_TAIL, d->tx_tail)) { d->last_error = GLH_EIO; return -1; }
        d->cache_pos = 0;
        d->cache_len = chunk;
        d->bytes_read += chunk;
        glh_idle_touch(&d->idle);
    }
    return (long long)delivered;
}

/* ------------------------------------------------------------------ ring writes (RX: host -> guest) */
long long glh_dma_write(glh_dma *d, const void *src, size_t n)
{
    const uint8_t *in = (const uint8_t *)src;
    size_t done = 0;
    while (done < n) {
        if (cancelled(d)) { d->last_error = GLH_EPIPE; return done ? (long long)done : -1; }
        uint32_t tail;
        int rc = read_cursor(d, DMA_OFF_RX_TAIL, &tail);
        if (rc < 0) { d->last_error = GLH_EIO; return done ? (long long)done : -1; }
        if (rc == 0) { glh_idle_wait(&d->idle); continue; }
        uint32_t used = d->rx_head - tail;
        if (used > DMA_RING_CAP) {
            glh_log("GLHOST_DMA_BAD_RX head=%u tail=%u", d->rx_head, tail);
            d->last_error = GLH_EPROTO;
            return -1;
        }
        uint32_t free_b = DMA_RING_CAP - used;
        if (free_b == 0) { glh_idle_wait(&d->idle); continue; }
        uint32_t pos = d->rx_head % DMA_RING_CAP;
        uint32_t chunk = DMA_RING_CAP - pos;
        if (chunk > free_b) chunk = free_b;
        if (chunk > n - done) chunk = (uint32_t)(n - done);
        rc = glh_dma_mem_write(d, DMA_OFF_RX_RING + pos, in + done, chunk);
        if (rc) { d->last_error = GLH_EIO; return done ? (long long)done : -1; }
        MemoryBarrier();
        d->rx_head += chunk;
        if (publish_cursor(d, DMA_OFF_RX_HEAD, d->rx_head)) { d->last_error = GLH_EIO; return -1; }
        done += chunk;
        d->bytes_written += chunk;
        glh_idle_touch(&d->idle);
    }
    return (long long)done;
}

void glh_dma_signal_stop(glh_dma *d)
{
    uint32_t one = 1;
    if (d && d->remote) glh_dma_mem_write(d, DMA_OFF_STOP, &one, 4);
}

void glh_dma_close(glh_dma *d)
{
    if (!d) return;
    if (d->own_handle && d->process) CloseHandle(d->process);
    d->process = NULL;
    d->remote = NULL;
    free(d->cache);
    d->cache = NULL;
    glh_idle_close(&d->idle);
}

/* ------------------------------------------------------------------ attach (section 5.3) */
static int read_config(const char *path, uint32_t *pid, uint64_t *base, uint64_t *size, uint64_t *ctime)
{
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    char line[512];
    size_t n = fread(line, 1, sizeof line - 1, f);
    fclose(f);
    line[n] = 0;
    unsigned long p = 0;
    unsigned long long b = 0, s = 0, c = 0;
    if (sscanf(line, "%lu %llx %llx %llx", &p, &b, &s, &c) != 4) return 0;
    *pid = (uint32_t)p; *base = b; *size = s; *ctime = c;
    return 1;
}

static int image_is_qemu(HANDLE h)
{
    wchar_t path[2048];
    DWORD len = sizeof path / sizeof path[0];
    if (!QueryFullProcessImageNameW(h, 0, path, &len)) return 0;
    const wchar_t *last = path;
    for (const wchar_t *p = path; *p; p++)
        if (*p == L'\\' || *p == L'/') last = p + 1;
    return _wcsicmp(last, L"qemu-system-x86_64.exe") == 0;
}

int glh_dma_attach(glh_dma *d, const uint8_t payload[28], const char *config_path, volatile LONG *cancel)
{
    memset(d, 0, sizeof *d);
    resolve_ntdll();
    d->cancel = cancel;
    glh_idle_init(&d->idle);
    if (!config_path || !*config_path) return -1;

    uint32_t pid = 0;
    uint64_t base = 0, ram = 0, ctime = 0;
    DWORD start = GetTickCount();
    while (!read_config(config_path, &pid, &base, &ram, &ctime)) {
        if (cancel && *cancel) return -1;
        if (GetTickCount() - start > 5000) return -1;
        Sleep(5);
    }

    uint32_t phys = rd_u32(payload + 0), length = rd_u32(payload + 4), version = rd_u32(payload + 8);
    const uint8_t *nonce = payload + 12;
    if (version != 2 || length != DMA_REGION_BYTES || ram != 0x20000000ull) return -1;
    if (phys < 0x100000u || (phys & 4095u) != 0 || (uint64_t)phys + length > ram) return -1;
    if (base == 0 || base + phys < base || base + phys + length < base + phys) return -1;

    HANDLE h = OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_LIMITED_INFORMATION,
                           FALSE, pid);
    if (!h) return -1;
    d->process = h;
    d->own_handle = 1;
    d->pid = pid;
    d->phys = phys;
    FILETIME ft_create, ft_exit, ft_kernel, ft_user;
    if (!GetProcessTimes(h, &ft_create, &ft_exit, &ft_kernel, &ft_user)) goto fail;
    if ((((uint64_t)ft_create.dwHighDateTime << 32) | ft_create.dwLowDateTime) != ctime) goto fail;
    if (!image_is_qemu(h)) goto fail;

    uint8_t *addr = (uint8_t *)(uintptr_t)(base + phys);
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQueryEx(h, addr, &mbi, sizeof mbi) != sizeof mbi) goto fail;
    if (mbi.State != MEM_COMMIT || mbi.Protect != PAGE_READWRITE) goto fail;
    if ((uintptr_t)addr + length > (uintptr_t)mbi.BaseAddress + mbi.RegionSize) goto fail;
    d->remote = addr;

    uint8_t hdr[44];
    if (glh_dma_mem_read(d, 0, hdr, sizeof hdr)) goto fail;
    if (memcmp(hdr, "NBT_DMA_RING_V2\0", 16) != 0) goto fail;
    if (rd_u32(hdr + 16) != version || rd_u32(hdr + 20) != length || rd_u32(hdr + 24) != DMA_RING_CAP) goto fail;
    if (memcmp(hdr + 28, nonce, 16) != 0) goto fail;
    uint32_t w64 = 1;
    if (glh_dma_mem_read(d, DMA_OFF_ATTACHED, &w64, 4) || w64 != 0) goto fail;
    static const uint32_t counters[4] = { DMA_OFF_TX_HEAD, DMA_OFF_TX_TAIL, DMA_OFF_RX_HEAD, DMA_OFF_RX_TAIL };
    for (int i = 0; i < 4; i++) {
        uint32_t v = 1;
        if (read_cursor(d, counters[i], &v) != 1 || v != 0) goto fail;
    }
    if (!alloc_cache(d)) goto fail;
    d->tx_tail = 0;
    d->rx_head = 0;
    uint32_t one = 1;
    if (glh_dma_mem_write(d, DMA_OFF_ATTACHED, &one, 4)) goto fail;
    glh_log("GLHOST_DMA_ATTACHED pid=%u physical=0x%x bytes=%u bounded_adapter_region=1", pid, phys, length);
    return 0;
fail:
    glh_dma_close(d);
    return -1;
}
