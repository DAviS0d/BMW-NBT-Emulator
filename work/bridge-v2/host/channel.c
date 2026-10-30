/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): record channel - legacy stdio, QEMU chardev socket + stdin lifetime pipe, DMA.
 */
#include "glh.h"
#include <ws2tcpip.h>
#include <stdio.h>
#include <stdlib.h>

struct glh_channel {
    int socket_mode;
    SOCKET sock;
    volatile LONG sock_closed;
    HANDLE in, out;                 /* stdio mode */
    HANDLE control_thread;
    volatile LONG closing;
    volatile LONG control_eof;
    volatile LONG cancel;           /* control EOF or closing */
    uint64_t rx_bytes, tx_bytes;
    int port;
    glh_dma *dma;
};

static void close_socket_once(glh_channel *c)
{
    if (InterlockedExchange(&c->sock_closed, 1) == 0 && c->sock != INVALID_SOCKET) closesocket(c->sock);
}

static DWORD WINAPI control_main(LPVOID arg)
{
    glh_channel *c = (glh_channel *)arg;
    HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
    char buf[4096];
    for (;;) {
        DWORD got = 0;
        BOOL ok = in && in != INVALID_HANDLE_VALUE && ReadFile(in, buf, sizeof buf, &got, NULL);
        if (!ok || got == 0) break;
    }
    if (!c->closing) {
        InterlockedExchange(&c->control_eof, 1);
        InterlockedExchange(&c->cancel, 1);
        close_socket_once(c);
    }
    return 0;
}

static int parse_port(const char *s, int *out)
{
    long v = 0;
    if (!s || !*s) return 0;
    for (const char *p = s; *p; p++) {
        if (*p < '0' || *p > '9') return 0;
        v = v * 10 + (*p - '0');
        if (v > 65535) return 0;
    }
    if (v < 1) return 0;
    *out = (int)v;
    return 1;
}

int glh_channel_open(glh_channel **out)
{
    glh_channel *c = (glh_channel *)calloc(1, sizeof *c);
    if (!c) return 1;
    c->sock = INVALID_SOCKET;
    *out = c;
    const char *port_env = getenv("GLHOST_QEMU_PORT");
    if (!port_env || !*port_env) {
        c->in = GetStdHandle(STD_INPUT_HANDLE);
        c->out = GetStdHandle(STD_OUTPUT_HANDLE);
        return 0;
    }
    c->socket_mode = 1;
    WSADATA wsa;
    int err = WSAStartup(MAKEWORD(2, 2), &wsa);
    if (err) { glh_log("GLHOST_SOCKET_ERROR WSAStartup=%d", err); return 2; }
    if (!parse_port(port_env, &c->port)) { glh_log("GLHOST_SOCKET_ERROR invalid GLHOST_QEMU_PORT"); return 2; }

    struct sockaddr_in sa;
    memset(&sa, 0, sizeof sa);
    sa.sin_family = AF_INET;
    sa.sin_port = htons((u_short)c->port);
    sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    DWORD start = GetTickCount();
    for (;;) {
        SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        if (s != INVALID_SOCKET && connect(s, (struct sockaddr *)&sa, sizeof sa) == 0) { c->sock = s; break; }
        int e = WSAGetLastError();
        if (s != INVALID_SOCKET) closesocket(s);
        if (GetTickCount() - start >= 10000) {
            glh_log("GLHOST_SOCKET_ERROR connect port=%d error=%d", c->port, e);
            return 2;
        }
        Sleep(25);
    }
    BOOL one = TRUE;
    if (setsockopt(c->sock, IPPROTO_TCP, TCP_NODELAY, (const char *)&one, sizeof one) != 0) {
        glh_log("GLHOST_SOCKET_ERROR TCP_NODELAY=%d", WSAGetLastError());
        return 2;
    }
    c->control_thread = CreateThread(NULL, 0, control_main, c, 0, NULL);
    if (!c->control_thread) {
        glh_log("GLHOST_SOCKET_ERROR control thread=%lu", (unsigned long)GetLastError());
        return 2;
    }
    glh_log("GLHOST_NATIVE_SOCKET_CONNECTED port=%d", c->port);
    return 0;
}

/* one transport read: >0 bytes, 0 EOF, -1 error */
static long long base_read(glh_channel *c, void *dst, size_t n)
{
    if (c->socket_mode) {
        for (;;) {
            int want = n > 0x40000000u ? 0x40000000 : (int)n;
            int r = recv(c->sock, (char *)dst, want, 0);
            if (r > 0) { c->rx_bytes += (uint64_t)r; return r; }
            if (r == 0) return 0;
            int e = WSAGetLastError();
            if (e == WSAEINTR && !c->cancel) continue;   /* EINTR: retry */
            return -1;                                   /* EAGAIN / ECONNRESET / EIO */
        }
    }
    DWORD got = 0;
    DWORD want = n > 0x40000000u ? 0x40000000u : (DWORD)n;
    if (!ReadFile(c->in, dst, want, &got, NULL)) return GetLastError() == ERROR_BROKEN_PIPE ? 0 : -1;
    return got;
}

int glh_channel_read_exact(glh_channel *c, void *dst, size_t n)
{
    uint8_t *p = (uint8_t *)dst;
    while (n > 0) {
        long long r = c->dma ? glh_dma_read(c->dma, p, n) : base_read(c, p, n);
        if (r <= 0) return 0;
        p += r;
        n -= (size_t)r;
    }
    return 1;
}

int glh_channel_write_base(glh_channel *c, const void *src, size_t n)
{
    const char *p = (const char *)src;
    while (n > 0) {
        if (c->socket_mode) {
            int want = n > 0x40000000u ? 0x40000000 : (int)n;
            int r = send(c->sock, p, want, 0);
            if (r <= 0) {
                if (r < 0 && WSAGetLastError() == WSAEINTR && !c->cancel) continue;
                return -1;
            }
            c->tx_bytes += (uint64_t)r;
            p += r;
            n -= (size_t)r;
        } else {
            DWORD put = 0;
            if (!WriteFile(c->out, p, n > 0x40000000u ? 0x40000000u : (DWORD)n, &put, NULL) || put == 0) return -1;
            p += put;
            n -= put;
        }
    }
    return 0;
}

int glh_channel_write(glh_channel *c, const void *src, size_t n)
{
    if (!c->dma) return glh_channel_write_base(c, src, n);
    long long r = glh_dma_write(c->dma, src, n);
    return r == (long long)n ? 0 : -1;
}

int glh_channel_is_socket(glh_channel *c) { return c->socket_mode; }
volatile LONG *glh_channel_cancel_flag(glh_channel *c) { return &c->cancel; }
void glh_channel_use_dma(glh_channel *c, glh_dma *d) { c->dma = d; }
glh_dma *glh_channel_dma(glh_channel *c) { return c->dma; }

void glh_channel_shutdown(glh_channel *c)
{
    if (!c || !c->socket_mode) return;
    InterlockedExchange(&c->closing, 1);
    InterlockedExchange(&c->cancel, 1);
    close_socket_once(c);
    int joined = 0;
    if (c->control_thread) {
        DWORD start = GetTickCount();
        for (;;) {
            CancelSynchronousIo(c->control_thread);
            if (WaitForSingleObject(c->control_thread, 50) == WAIT_OBJECT_0) { joined = 1; break; }
            if (GetTickCount() - start >= 2000) break;
        }
        CloseHandle(c->control_thread);
        c->control_thread = NULL;
    }
    WSACleanup();
    glh_log("GLHOST_NATIVE_SOCKET_COUNTS rx=%llu tx=%llu", (unsigned long long)c->rx_bytes, (unsigned long long)c->tx_bytes);
    glh_log("GLHOST_NATIVE_SOCKET_STOP control_eof=%d control_joined=%d", c->control_eof ? 1 : 0, joined);
}
