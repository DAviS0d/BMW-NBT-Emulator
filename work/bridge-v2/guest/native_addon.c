/* Dedicated bounded mailbox; the original graphics/input bridge is unchanged. */
#include "nbt_guest.h"
NBT_IMPORT void *dlsym(void *, const char *);
NBT_IMPORT void *dlopen(const char *, int);

typedef struct native_mailbox {
    uint32_t magic, version;
    volatile uint32_t command_sequence, power, torque;
    volatile uint32_t event_sequence, selected, applied_sequence, status;
} native_mailbox;
static native_mailbox *g_mailbox;
static uint32_t g_command_seen;
static void mailbox_init(void)
{
    if (g_mailbox) return;
    ThreadCtl(QNX_NTO_TCTL_IO, (void *)0);
    void *page=mmap64(0,4096,QNX_PROT_RW,QNX_MAP_PHYS_ANON,-1,0);
    if (page==(void *)-1) { NBT_LOG("NBT_NATIVE_MAILBOX_ALLOC_FAILED errno=%d\n",nbt_errno()); return; }
    int64_t physical=0;
    size_t contiguous=0;
    if (mem_offset64(page,-1,4096,&physical,&contiguous) || contiguous<4096 || physical<0 || physical>0x1ffff000) {
        NBT_LOG("NBT_NATIVE_MAILBOX_ADDRESS_FAILED errno=%d\n",nbt_errno()); return;
    }
    memset(page,0,4096);
    g_mailbox=page;
    g_mailbox->magic=0x5854424e;
    g_mailbox->version=1;
    g_mailbox->status=1;
    nbt_mb();
    NBT_LOG("NBT_NATIVE_MAILBOX physical=0x%x bytes=4096 version=1\n",(uint32_t)physical);
}
void nbt_native_mailbox_selection(uint32_t selected)
{
    if (!g_mailbox) return;
    g_mailbox->selected=selected;
    nbt_mb();
    ++g_mailbox->event_sequence;
}
extern void nbt_native_menu_tick(void);
static void mailbox_tick(void)
{
    if (!g_mailbox) return;
    uint32_t sequence=g_mailbox->command_sequence;
    if (sequence!=g_command_seen) {
        nbt_mb();
        uint32_t power=g_mailbox->power,torque=g_mailbox->torque;
        if (power<=100 && torque<=100 && sequence==g_mailbox->command_sequence && nbt_sports_update(power,torque)==0) {
            g_command_seen=sequence;
            g_mailbox->applied_sequence=sequence;
        }
    }
    /* Host commands begin only after the native controller is initialized. */
    if(g_command_seen) nbt_native_menu_tick();
    nbt_sports_tick();
}
NBT_API unsigned eglSwapBuffers(void *display,void *surface)
{
    mailbox_tick();
    typedef unsigned (*swap_function)(void *,void *);
    static swap_function original;
    if (!original) {
        void *handle=dlopen("libnbtgl.so",6);
        if (!handle) handle=dlopen("libnbtgl.so",2);
        if (handle) original=(swap_function)dlsym(handle,"eglSwapBuffers");
        if ((void *)original==(void *)eglSwapBuffers) original=0;
    }
    return original?original(display,surface):0;
}
__attribute__((constructor)) static void mailbox_constructor(void) { mailbox_init(); }
