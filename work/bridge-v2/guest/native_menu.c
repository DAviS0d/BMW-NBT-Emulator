/* Version-bound original menu adapters; firmware identity checked by builder. */
#include "nbt_guest.h"
NBT_IMPORT int mprotect(void *,size_t,int);
typedef uint32_t (*menu_event_fn)(void *,uint32_t,uint32_t,uint32_t);
static menu_event_fn original_menu;
static volatile int tick_busy;
extern void nbt_native_mailbox_selection(uint32_t);
static uint32_t menu_event(void *self,uint32_t component,uint32_t event,uint32_t row)
{
    /* Original main menu model orders Navigation at row 3. Check the
       originating view exactly as the original handler does. */
    if((event&0x20000) && row==3) {
        uintptr_t view=*(uintptr_t *)((uint8_t *)self+0xa0);
        if(view) {
            uintptr_t vt=*(uintptr_t *)view;
            view+=(int32_t)*(uint32_t *)(vt-0x24);
            typedef uint32_t (*get_id)(void *);
            get_id id=(get_id)(*(uint32_t **)view)[2];
            if(id((void *)view)==component) {
                nbt_native_mailbox_selection(14);
                NBT_LOG("NBT_NATIVE_NAVIGATION_SELECTED row=%u\n",row);
                return 1;
            }
        }
    }
    return original_menu(self,component,event,row);
}
static void menu_tick_impl(void)
{
    typedef void *(*lookup_fn)(uint32_t);
    uintptr_t address=0x080ae8b0;
    __asm__ __volatile__("" : "+r"(address));
    void *vehicle_list=((lookup_fn)address)(32013);
    if(!vehicle_list) return;
    uint32_t *vt=*(uint32_t **)vehicle_list;
    typedef int (*find_fn)(void *,uint32_t);
    typedef void (*enable_fn)(void *,int,int);
    typedef int (*enabled_fn)(void *,int);
    int row=((find_fn)vt[0x8c/4])(vehicle_list,17);
    if(row>=0 && !((enabled_fn)vt[0x80/4])(vehicle_list,row)) {
        ((enable_fn)vt[0x7c/4])(vehicle_list,row,1);
        NBT_LOG("NBT_NATIVE_SPORT_MENU_ENABLED row=%d\n",row);
    }
}
void nbt_native_menu_tick(void)
{
    if(__sync_lock_test_and_set(&tick_busy,1)) return;
    menu_tick_impl();
    __sync_lock_release(&tick_busy);
}
static void jump(uint8_t *p,void *target)
{
    uint32_t displacement=(uint32_t)(uintptr_t)target-(uint32_t)(uintptr_t)(p+5);
    p[0]=0xe9; memcpy(p+1,&displacement,4);
}
static void *hook(uintptr_t address,void *replacement)
{
    uint8_t *p=(uint8_t *)address;
    const uint8_t prefix[6]={0x55,0x89,0xe5,0x57,0x56,0x53};
    if(memcmp(p,prefix,6)) return 0;
    uint8_t *trampoline=mmap64(0,4096,0x700,0x80002,-1,0);
    if(trampoline==(void *)-1) return 0;
    memcpy(trampoline,p,6); jump(trampoline+6,p+6);
    mprotect(trampoline,4096,0x500);
    if(nbt_native_writable_page(address&~4095u)) return 0;
    jump(p,replacement); p[5]=0x90;
    mprotect((void *)(address&~4095u),4096,0x500);
    return trampoline;
}
__attribute__((constructor)) static void install(void)
{
    original_menu=(menu_event_fn)hook(0x081ad936,menu_event);
    NBT_LOG("NBT_NATIVE_MENU_INSTALLED navigation=%d\n",!!original_menu);
}
