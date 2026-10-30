/* © 2026 davisod & JEtsKi
 * nbt-glhost-v2 (bridge v2, host): process entry - environment contract, transport start, ordered shutdown.
 */
#include "glh.h"
#include <stdio.h>
#include <io.h>
#include <fcntl.h>

int main(void)
{
    glh_log_init();
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);

    glh_channel *ch = NULL;
    int rc = glh_channel_open(&ch);
    if (rc != 0) {
        fflush(stderr);
        return rc;
    }
    rc = glh_render_session(ch);       /* ends with the publisher stopped and the DMA stop word written */
    glh_channel_shutdown(ch);          /* socket counts + stop lines (socket mode only) */
    glh_render_release_dma();
    fflush(stderr);
    return rc;
}
