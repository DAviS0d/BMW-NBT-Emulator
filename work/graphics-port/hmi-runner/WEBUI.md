# NBT web interface

Run `RUN_WEBUI.cmd`, or run `py -3 webui.py` and open
<http://127.0.0.1:8877>.

The interface attaches to a running emulator automatically. **Start emulator**
launches the normal viewer if no emulator is running. **Stop** stops the emulator;
closing the browser leaves it running. Keep the server running while using the page.

The base display comes from the original renderer; integrated navigation uses its
own map surface in the same display. Buttons, arrow keys, Enter, Escape,
and the mouse wheel send commands through the existing native input session.
Controls become available after the original keyboard queue reports readiness.
Software CPU mode reached controller readiness in about 22 seconds in the latest test.

Startup prefers an installed 64-bit Python with Tkinter. Prepared boot images are
cached in `boot-cache/` and checked against the firmware, loader, reference image,
and clock settings before reuse. Changes to these inputs rebuild the image. Each
run owns a separate hard link, so stopping a VM preserves the cache. Repeated
desktop launches reuse the running emulator instead of starting another VM.

The server listens only on this computer, on port 8877, and uses Python's standard
library; integrated map/phone rendering additionally uses Pillow. No cloud hosting is required. The desktop and browser controls
use English labels; the original firmware supplies the text inside the live display.
