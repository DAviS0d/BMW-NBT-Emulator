/* Offline native coding input for this exact recovered HmiMain3D image.
 * Delivers the owner's unchanged NCD bytes through the ORIGINAL processEvent,
 * original DSIRead parser, original metadata and original listener callbacks.
 * No executable instructions, contexts, vtables or coding bytes are patched. */
#include <stdarg.h>
typedef unsigned U;
typedef unsigned char B;
extern int printf(const char *, ...);
extern int fflush(void *);
extern int pthread_create(U *, const void *, void *(*)(void *), void *);
extern int usleep(U);
extern void native_buf_ctor(void *) __asm__("_ZN9CHBBufferC1Ev");
extern void native_buf_dtor(void *) __asm__("_ZN9CHBBufferD1Ev");
extern void native_buf_copy(void *, const void *, U, U) __asm__("_ZN9CHBBuffer6copyToEPKvjj");
extern U native_buf_size(const void *) __asm__("_ZNK9CHBBuffer7getSizeEv");
extern int native_syslog_vlog(int, int, const char *, va_list)
    __asm__("_ZN8HBSyslog7vlogMsgEiNS_8SeverityEPKcPc");
#include "coding_payload.h"

struct NativeBuffer { void *data; };
/* Original processEvent reads event ID at +0xc, tag at +0x10 and an actual
 * CHBBuffer at +0x14. It does not dispatch through the event's header. */
struct NativeEvent { U opaque_header[3], id, tag; struct NativeBuffer payload; };
static volatile U gate;
static U worker_id;
volatile int nbt_offline_syset_status;
volatile U nbt_offline_syset_desc, nbt_offline_syset_variant;
volatile U nbt_offline_syset_thread, nbt_offline_syset_client;
volatile U nbt_offline_syset_captured_client, nbt_offline_syset_captured_listener;
static volatile U capture_gate;

static U word(U address) { return *(volatile U *)address; }
static int plausible(U p) { return p >= 0x08048000U && p < 0xf0000000U && !(p & 3U); }

/* Every step follows the original native ownership path identified in the
 * executable. No heap scanning or guessed object offsets are used. */
static const char *find_text(const char *text, const char *needle)
{
    if (!text) return 0;
    for (; *text; ++text) {
        const char *a = text, *b = needle;
        while (*b && *a == *b) { ++a; ++b; }
        if (!*b) return text;
    }
    return 0;
}

static U formatted_pointer(const char *text)
{
    U result = 0, digits = 0;
    if (!text) return 0;
    while (*text == ' ' || *text == '\t') ++text;
    if (text[0] == '0' && (text[1] == 'x' || text[1] == 'X')) text += 2;
    for (; *text; ++text) {
        U digit;
        if (*text >= '0' && *text <= '9') digit = (U)(*text - '0');
        else if (*text >= 'a' && *text <= 'f') digit = (U)(*text - 'a') + 10U;
        else if (*text >= 'A' && *text <= 'F') digit = (U)(*text - 'A') + 10U;
        else break;
        if (++digits > 8U) return 0;
        result = (result << 4) | digit;
    }
    return digits ? result : 0;
}

/* 0x08f99014 already formats this constructor message before calling
 * HBSyslog::logMsg at 0x08f9906e. Inspect only that immutable formatted text;
 * do not consume, format or copy the caller's variadic argument cursor. */
static void capture_constructor(const char *text)
{
    if (nbt_offline_syset_captured_client ||
        !find_text(text, "CHMISysetClientConfigImpl")) return;
    const char *this_text = find_text(text, "this ");
    const char *listener_text = find_text(text, "listener ");
    if (!this_text || !listener_text) return;
    U client = formatted_pointer(this_text + 5);
    U listener = formatted_pointer(listener_text + 9);
    if (!plausible(client) || !plausible(listener) || listener < 0xc0U ||
        !plausible(listener - 0xc0U)) return;
    if (!__sync_bool_compare_and_swap(&capture_gate, 0, 1)) return;
    nbt_offline_syset_captured_listener = listener;
    __sync_synchronize();
    nbt_offline_syset_captured_client = client;
}

int nbt_preserving_syslog(int domain, int severity, const char *format, ...)
    __asm__("_ZN8HBSyslog6logMsgEiNS_8SeverityEPKcz");
int nbt_preserving_syslog(int domain, int severity, const char *format, ...)
{
    capture_constructor(format);
    va_list arguments;
    va_start(arguments, format);
    int result = native_syslog_vlog(domain, severity, format, arguments);
    va_end(arguments);
    return result;
}

static U published_client(void)
{
    U client = nbt_offline_syset_captured_client;
    if (!plausible(client)) return 0;
    __sync_synchronize();
    U listener = nbt_offline_syset_captured_listener;
    if (!plausible(listener) || listener < 0xc0U) return 0;
    U thread = listener - 0xc0U;
    if (!plausible(thread) || word(thread) != 0x0963b220U) return 0;
    if (word(thread + 0xc4U) != client || word(client) != 0x09760e40U) return 0;
    if (word(0x09760e40U + 0x28U) != 0x08f99da0U) return 0;
    if (!plausible(word(0x099a7d14U))) return 0;
    /* thread+c4 is assigned at 0x089eb790 after the constructor returns. */
    if (word(thread + 0xc4U) != client) return 0;
    nbt_offline_syset_thread = thread; nbt_offline_syset_client = client;
    return client;
}

int nbt_offline_syset_apply(void *instance)
{
    U client = (U)instance;
    if (!plausible(client) || word(client) != 0x09760e40U ||
        word(0x09760e40U + 0x28U) != 0x08f99da0U ||
        !plausible(word(0x099a7d14U))) return -2;
    if (!__sync_bool_compare_and_swap(&gate, 0, 1)) return nbt_offline_syset_status;
    nbt_offline_syset_status = 2;
    struct NativeEvent event;
    event.opaque_header[0] = event.opaque_header[1] = event.opaque_header[2] = 0;
    event.id = 0x80000000U;
    event.tag = word(client + 0x18U); /* Preserve the client's native generation tag. */
    native_buf_ctor(&event.payload);
    native_buf_copy(&event.payload, nbt_native_coding_dsi, sizeof(nbt_native_coding_dsi), 0);
    U actual = native_buf_size(&event.payload);
    if (actual != sizeof(nbt_native_coding_dsi)) {
        printf("NBT_OFFLINE_SYSET buffer_error expected=%u actual=%u\n", (U)sizeof(nbt_native_coding_dsi), actual);
        native_buf_dtor(&event.payload); nbt_offline_syset_status = -3; fflush(0); return -3;
    }
    printf("NBT_OFFLINE_SYSET deliver client=%p native_event=%08x bytes=%u version=%u.%u.%u tag=%08x source=%s\n",
           instance, 0x08f99da0U, actual, NBT_CODING_MAJOR, NBT_CODING_MINOR,
           NBT_CODING_PATCH, event.tag, NBT_CODING_SOURCE_SHA256);
    fflush(0);
    /* In ET_DYN an optimized direct rel32 call would acquire this DSO's load
     * bias. Read a volatile pointer so the call uses the absolute native VA. */
    void (*volatile native_event)(void *, const struct NativeEvent *) =
        (void (*)(void *, const struct NativeEvent *))(U)0x08f99da0U;
    native_event(instance, &event);
    native_buf_dtor(&event.payload);
    nbt_offline_syset_status = 3;
    printf("NBT_OFFLINE_SYSET native_event_returned client=%p tag=%08x\n", instance, word(client + 0x18U));
    fflush(0);
    return 3;
}

static void *worker(void *unused)
{
    (void)unused;
    nbt_offline_syset_status = 1;
    printf("NBT_OFFLINE_SYSET waiting_native_client bytes=%u version=%u.%u.%u\n",
           (U)sizeof(nbt_native_coding_dsi), NBT_CODING_MAJOR, NBT_CODING_MINOR, NBT_CODING_PATCH);
    fflush(0);
    for (U attempts = 0; attempts < 30000U; ++attempts) {
        U client = published_client();
        if (client) { nbt_offline_syset_apply((void *)client); return 0; }
        usleep(1000);
    }
    nbt_offline_syset_status = -1;
    printf("NBT_OFFLINE_SYSET native_client_timeout captured_client=%08x captured_listener=%08x root=%08x\n",
           nbt_offline_syset_captured_client, nbt_offline_syset_captured_listener, word(0x099a7d14U));
    fflush(0); return 0;
}

void _init(void)
{
    nbt_offline_syset_status = 0;
    int result = pthread_create(&worker_id, 0, worker, 0);
    if (result) { nbt_offline_syset_status = -4; printf("NBT_OFFLINE_SYSET pthread_create_error=%d\n", result); fflush(0); }
}
