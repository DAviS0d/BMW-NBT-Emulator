# © 2026 davisod & JEtsKi
"""Show actual original-NBT renderer frames in a Windows Tk window.

The menu is rendered by the original HMI. Keyboard navigation posts original
controller events to its native queue and waits for the adapter readiness reply.
"""
import argparse
import hashlib
import json
import math
import queue
import re
import sys
import threading
import time
import traceback
import socket
import io
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
# Default profile: the clean-room GLES bridge (work/bridge-v2, docs/RAPORT_CLEANROOM.md),
# i.e. the legacy DMA image with only libnbtgl.so replaced, plus its renderer.
# The _prio image also starts the MTP bridge at priority 13, so the keyboard is
# ready at ~14 s instead of ~98 s (work/bridge-v2/build_ifs_prio.py).
DEFAULT_IFS = WORKSPACE / "work/bridge-v2/ifs/walthread_keyboard_dma_v2_prio.ifs"
NATIVE_IFS = WORKSPACE / "work/bridge-v2/ifs/walthread_keyboard_dma_v2_native.ifs"
DEFAULT_RENDERER = WORKSPACE / "work/bridge-v2/host/nbt-glhost-v2.exe"
# --legacy / --fast: the previous default DMA image (qemu-mhi2-derived bridge).
LEGACY_IFS = WORKSPACE / "work/graphics-port/guest/walthread_keyboard_dma_navigation_hmi_probe_app12_trace_quiet.ifs"
PREVIOUS_IFS = WORKSPACE / "work/graphics-port/guest/walthread_keyboard_batched_spin_navigation_hmi_probe_app12_trace_quiet.ifs"
SOFTWARE_IFS = WORKSPACE / "work/graphics-port/guest/walthread_keyboard_ready_navigation_hmi_probe.ifs"
NATIVE_CONTROLS = WORKSPACE / "work/graphics-port/native-controls"
# --fast: the legacy DMA image with the bulk-ring/off-path-publication renderer
# (host/perf-batch, docs/RAPORT_PERF_2026-10-30.md).
FAST_RENDERER = WORKSPACE / "work/graphics-port/host/nbt-glhost-dma-fast.exe"
# Everything the default profile needs at run time. Firmware-derived items are
# not in the public repository; the viewer refuses to start without them.
DEFAULT_PROFILE_FILES = (
    DEFAULT_IFS,                                                            # firmware image (v2)
    WORKSPACE / "outputs/NBT_emulation_research/btld_00001275/Intel/fs/sda2/appimage.ifs",  # firmware
    WORKSPACE / "work/graphics-port/host/shader-cache",                     # firmware-derived shaders
    DEFAULT_RENDERER,
    WORKSPACE / "work/graphics-port/host/angle/angle-x64/bin/libGLESv2.dll",
    WORKSPACE / "work/emulation-tools/qemu-portable/qemu-system-x86_64.exe",
)
STARTUP_SCREEN = WORKSPACE / "work/startup-analysis"
STARTUP_FRAME_MS = 40
VIEWER_ACTIONS = ("up", "down", "select", "back", "menu", "option", "tilt_left", "tilt_right",
                  "tilt_up", "tilt_down", "radio", "media", "nav", "tel")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class LiveViewer:
    def __init__(self, root, smoke_seconds=None, software=False, previous=False, fast=False, legacy=False, native=False):
        self.root = root
        self.smoke_seconds = smoke_seconds
        self.software = software
        self.native_extensions = native
        self.active_extension = None
        self.extension_surface = None
        self.extension_photo = None
        self.extension_frame = None
        self.extension_loading = False
        self.extension_last_poll = 0
        import run_hmi
        self.accelerator = 'tcg' if software or not run_hmi.hypervisor_available() else 'whpx'
        self.dma_transport = not software and not previous
        self.poll_ms = 16 if self.dma_transport else 33
        if native:
            self.source_ifs, self.renderer_path = NATIVE_IFS, DEFAULT_RENDERER
        elif software or previous:
            self.source_ifs, self.renderer_path = (SOFTWARE_IFS if software else PREVIOUS_IFS), None
        elif fast:
            self.source_ifs, self.renderer_path = LEGACY_IFS, FAST_RENDERER
        elif legacy:
            self.source_ifs, self.renderer_path = LEGACY_IFS, None
        else:
            self.source_ifs, self.renderer_path = DEFAULT_IFS, DEFAULT_RENDERER
        self.messages = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.worker_finished = False
        self.worker_result = None
        self.worker_error = None
        self.controller = None
        self.controller_configured = False
        self.controller_cleanup_completed = False
        self.control_buttons = []
        self.run_directory = None
        self.close_requested = False
        self.close_reason = None
        self.first_frame_time = None
        self.last_frame_stamp = None
        self.presentations_seen = False
        self.full_photo = None
        self.display_photo = None
        self.frame_loads = 0
        self.started = time.monotonic()
        self.proof_directory = HERE / "viewer-runs" / f"viewer-{time.time_ns()}"
        self.proof_directory.mkdir(parents=True)
        self.proof = {
            "test": "ACTUAL_ORIGINAL_NBT_LIVE_VIEWER",
            "started_utc": utc_now(), "source_ifs": str(self.source_ifs),
            "accelerator": self.accelerator,
            "frame_publication": "legacy_pixel_writes" if software else "cached_rgb_block",
            "renderer_transport": "bounded_guest_dma" if self.dma_transport else "legacy",
            "renderer": str(self.renderer_path) if self.renderer_path else "default",
            "frame_poll_ms": self.poll_ms,
            "button_hold_seconds": .020 if self.dma_transport else .075,
            "smoke_seconds_after_first_display": smoke_seconds,
            "native_input_enabled": True,
            "controller_configured_event_seen": False,
            "controller_event_counts": {},
            "actual_frame_displayed": False,
            "cleanup_completed": False,
            "events": [],
        }

        root.title("BMW NBT — Live viewer")
        root.configure(background="#101010")
        root.protocol("WM_DELETE_WINDOW", lambda: self.request_close("window_close"))
        screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
        self.max_frame_width = max(320, min(1280, screen_width - 96))
        self.max_frame_height = max(180, min(480, screen_height - 220))
        self.proof["screen_dimensions"] = [screen_width, screen_height]
        root.geometry(f"{self.max_frame_width + 28}x{self.max_frame_height + 172}")
        root.minsize(min(640, screen_width - 40), min(320, screen_height - 60))

        top = tk.Frame(root, background="#101010")
        top.pack(fill="x", padx=14, pady=(10, 6))
        tk.Label(top, text="BMW NBT · Live original firmware display",
                 background="#101010", foreground="#f0f0f0", font=("Segoe UI", 12)).pack(side="left")
        self.stop_button = ttk.Button(top, text="Stop", command=self.request_stop)
        self.stop_button.pack(side="right")
        frame = tk.Frame(root, background="black", width=self.max_frame_width,
                         height=self.max_frame_height)
        frame.pack(fill="both", expand=True, padx=14)
        frame.pack_propagate(False)
        self.image_label = tk.Label(frame, text="Starting QNX and the original interface…",
                                    background="black", foreground="#b8b8b8", font=("Segoe UI", 11))
        self.image_label.place(relx=.5, rely=.5, anchor="center")
        self._start_startup_screen()
        controls = tk.Frame(root, background="#101010")
        controls.pack(fill="x", padx=14, pady=(8, 0))
        for label, action in (("↑", "up"), ("↓", "down"), ("OK", "select"),
                              ("Back", "back"), ("Menu", "menu")):
            button = ttk.Button(controls, text=label, width=9, state="disabled", takefocus=False,
                                command=lambda name=action: self._send_action(name, "button"))
            button.pack(side="left", padx=(0, 6))
            button.bind("<Return>", lambda event: self._send_action("select", "keyboard"))
            self.control_buttons.append(button)
        self.controller_note = tk.StringVar(value="Waiting for the keyboard adapter…")
        tk.Label(controls, textvariable=self.controller_note, background="#101010",
                 foreground="#b8b8b8", anchor="w", font=("Segoe UI", 9)).pack(side="left", padx=(5, 0))
        # Remaining iDrive controls: tilt and console keys (native key codes in session.py).
        extra = tk.Frame(root, background="#101010")
        extra.pack(fill="x", padx=14, pady=(6, 0))
        for label, action in (("◀", "tilt_left"), ("▶", "tilt_right"), ("▲", "tilt_up"),
                              ("▼", "tilt_down"), ("OPTION", "option"), ("RADIO", "radio"),
                              ("MEDIA", "media"), ("NAV", "nav"), ("TEL", "tel")):
            button = ttk.Button(extra, text=label, width=7, state="disabled", takefocus=False,
                                command=lambda name=action: self._send_action(name, "button"))
            button.pack(side="left", padx=(0, 6))
            self.control_buttons.append(button)
        self.status = tk.StringVar(value="Starting… Waiting for the first rendered frame.")
        tk.Label(root, textvariable=self.status, background="#101010", foreground="#d0d0d0",
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(7, 0))
        tk.Label(root, text="↑ / ↓ or mouse wheel · Enter = OK · Esc/Backspace = Back · M = Menu · "
                            "← / → = tilt (Shift+↑/↓ up/down) · O = Option · "
                            "F1 Menu · F2 Radio · F3 Media · F4 Nav · F5 Tel",
                 background="#101010", foreground="#999999", anchor="w", font=("Segoe UI", 9)).pack(
                     fill="x", padx=14, pady=(3, 10))
        for sequence, action in (("<Up>", "up"), ("<Down>", "down"), ("<Return>", "select"),
                                 ("<Escape>", "back"), ("<m>", "menu"), ("<M>", "menu"),
                                 ("<BackSpace>", "back"), ("<o>", "option"), ("<O>", "option"),
                                 ("<Left>", "tilt_left"), ("<Right>", "tilt_right"),
                                 ("<Shift-Up>", "tilt_up"), ("<Shift-Down>", "tilt_down"),
                                 ("<F1>", "menu"), ("<F2>", "radio"), ("<F3>", "media"),
                                 ("<F4>", "nav"), ("<F5>", "tel")):
            root.bind(sequence, lambda event, name=action: self._send_action(name, "keyboard"))
        root.bind("<MouseWheel>", self._wheel)
        self._event("window_created")
        self.worker = threading.Thread(target=self._run_vm, name="original-nbt-vm", daemon=False)
        self.worker.start()
        root.after(self.poll_ms, self._poll)

    def _event(self, name, **details):
        self.proof["events"].append({"event": name, "elapsed_seconds": time.monotonic() - self.started,
                                    **details})

    def _run_vm(self):
        result = None
        error_message = None
        try:
            if self.stop_event.is_set():
                result = {"stop_reason": "cancelled_before_launch"}
                return
            import run_hmi
            sys.path.insert(0, str(NATIVE_CONTROLS))
            from session import NativeInputSession
            def ready(info):
                self.messages.put(("ready", info))
                if not self.stop_event.is_set():
                    self.controller = NativeInputSession(
                        info, self.stop_event,
                        on_event=lambda event: self.messages.put(("controller", event)),
                        rotary_version=1,
                        native_extension=self.native_extensions,
                        button_hold_seconds=.020 if self.dma_transport else .075,
                        button_release_gap_seconds=0 if self.dma_transport else .075)
                    self.controller.start()
            result = run_hmi.run(
                self.source_ifs, seconds=3600, transport="virtio", input_port=0,
                virtio_port=1, input_virtio=True, keyboard_hal=True,
                synchronize_clock=False, instruction_counting=False,
                stop_event=self.stop_event,
                on_ready=ready, idle_sleep=True,
                capture_protocol=False, retain_boot_image=False,
                accelerator=self.accelerator,
                direct_renderer=not self.software,
                block_publication=not self.software,
                dma_transport=self.dma_transport,
                renderer_path=self.renderer_path)
        except BaseException as error:
            detail = traceback.format_exc()
            (self.proof_directory / "worker-error.txt").write_text(detail, encoding="utf-8")
            error_message = {"error": repr(error), "traceback": detail}
        finally:
            self.stop_event.set()
            try:
                if self.controller is not None:
                    self.controller.join(timeout=5)
                    self.controller_cleanup_completed = not self.controller.thread.is_alive()
                else:
                    self.controller_cleanup_completed = True
            except Exception as cleanup_error:
                self.controller_cleanup_completed = False
                if error_message is None:
                    error_message = {"error": "Controller cleanup: " + repr(cleanup_error)}
            if error_message:
                self.messages.put(("error", error_message))
            elif result is not None:
                self.messages.put(("done", result))

    # Startup screen: the emulator does not run EVA (NBTCarHUOne), which shows the
    # coded startup animation/splash on the car. Reproduce its choice from the
    # user's NCD with the original EVA resources until the HMI draws real content.
    def _start_startup_screen(self):
        self.startup_active = False
        self.startup_frames = []
        self.startup_splash = None
        try:
            sys.path.insert(0, str(STARTUP_SCREEN))
            from startup_screen import startup_screen, prepare_frames
            choice = startup_screen(1280, 480)
        except Exception as error:
            choice = {"error": repr(error)}
        self.proof["startup_screen"] = {k: v for k, v in choice.items() if k != "frames"}
        self.proof["startup_screen"]["animation_frames"] = len(choice.get("frames", []))
        if choice.get("error") and not choice.get("type"):
            return
        self.startup_active = True
        if choice["type"] == "black":
            self.image_label.configure(text="", image="")
            return
        if choice["type"] == "animation":
            self.startup_frames = choice.get("frames", [])
            if not self.startup_frames and choice.get("animation_source"):
                # First start: decode the original animation in the background
                # (about 20 s); this start shows the splash, later starts animate.
                threading.Thread(target=prepare_frames, args=(choice,), name="eva-frames",
                                 daemon=True).start()
                self._event("startup_animation_decoding_started", source=choice["animation_source"])
        try:
            self.startup_splash = self._startup_photo(choice["splash"]) if choice.get("splash") else None
        except tk.TclError as error:
            self.proof["startup_screen"]["load_error"] = str(error)
            return
        self._event("startup_screen_shown", type=choice["type"], emblem=choice.get("emblem"),
                    animation_frames=len(self.startup_frames))
        self._play_startup_frame(0)

    def _startup_photo(self, path):
        photo = tk.PhotoImage(master=self.root, file=path)
        divisor = max(1, math.ceil(photo.width() / self.max_frame_width),
                      math.ceil(photo.height() / self.max_frame_height))
        return photo if divisor == 1 else photo.subsample(divisor, divisor)

    def _play_startup_frame(self, index):
        if not self.startup_active:
            return
        if index < len(self.startup_frames):
            # Frames are loaded one at a time so the window never blocks.
            started = time.monotonic()
            try:
                self.startup_photo = self._startup_photo(self.startup_frames[index])
            except tk.TclError:
                self.startup_frames = []
                return self._play_startup_frame(0)
            self.image_label.configure(image=self.startup_photo, text="")
            spent = int((time.monotonic() - started) * 1000)
            self.root.after(max(1, STARTUP_FRAME_MS - spent), self._play_startup_frame, index + 1)
        elif self.startup_splash is not None:
            self.image_label.configure(image=self.startup_splash, text="")
            self._event("startup_animation_finished", frames=len(self.startup_frames))

    @staticmethod
    def _frame_has_content(payload, offset):
        """False for the renderer's initial clear and blank HMI frames."""
        sample = payload[offset::4099]
        return bool(sample) and max(sample) - min(sample) > 24

    def _set_controls_enabled(self, enabled):
        enabled = bool(enabled and not self.stop_event.is_set() and not self.worker_finished)
        for button in self.control_buttons:
            button.configure(state="normal" if enabled else "disabled")

    def _send_action(self, name, source="keyboard"):
        if self.active_extension:
            if name in ('back', 'menu'):
                self._close_extension()
                if name == 'back':
                    return 'break'
            elif name == 'option' and self.active_extension == 'navigation':
                self._navigation_destination()
                return 'break'
            elif self.extension_surface:
                surface = self.extension_surface
                kind = self.active_extension
                def dispatch():
                    try:
                        if kind == 'carplay':
                            surface.action('carplay', name)
                        else:
                            surface.action(name)
                    except Exception as error:
                        self.messages.put(('extension_error', str(error)))
                threading.Thread(target=dispatch, daemon=True).start()
                return 'break'
        if (name not in VIEWER_ACTIONS or
                not self.controller_configured or self.stop_event.is_set() or self.worker_finished or
                self.controller is None or not self.controller.ready):
            return "break"
        self.controller.action(name)
        self._event("native_action_requested", action=name, source=source)
        return "break"

    def _wheel(self, event):
        if event.delta:
            return self._send_action("up" if event.delta > 0 else "down", "mouse_wheel")
        return "break"

    def _handle_controller_event(self, event):
        kind = event.get("kind", "unknown")
        counts = self.proof["controller_event_counts"]
        counts[kind] = counts.get(kind, 0) + 1
        if kind == 'native_device_selected':
            self._activate_extension(event['source'])
            return
        if kind == 'extension_action':
            self._send_action(event['action'],'native_controller')
            return
        if kind == "controller_configured":
            self.controller_configured = True
            self.proof["controller_configured_event_seen"] = True
            self.proof["native_controller_handle"] = event.get("handle")
            self.proof["native_input_backend"] = event.get("backend")
            self._set_controls_enabled(True)
            self.controller_note.set("Keyboard connected · arrows, Enter, Esc, M")
            self._event("native_controller_configured", handle=event.get("handle"),
                        backend=event.get("backend"))
            self._write_verification()
        elif kind == "action_sent":
            self.proof["last_native_action"] = event.get("action")
            self.controller_note.set("Keyboard connected · command sent: " + str(event.get("action")))
            self._event("native_action_sent", action=event.get("action"), handle=event.get("handle"))
        elif kind == "action_rejected":
            self.controller_note.set("Command rejected by the native session.")
            self._event("native_action_rejected", action=event.get("action"), error=event.get("error"))
        elif kind in ("input_session_ended", "transport_closed", "input_session_closed"):
            self.controller_configured = False
            self._set_controls_enabled(False)
            self.controller_note.set("Keyboard stopped" if self.stop_event.is_set() else "Keyboard connection closed.")
            self._event(kind, error=event.get("error"))

    def _poll_messages(self):
        while True:
            try:
                kind, data = self.messages.get_nowait()
            except queue.Empty:
                return
            if kind == "ready":
                self.run_directory = Path(data["run_directory"])
                self.proof["run_directory"] = str(self.run_directory)
                self.proof["input_port"] = data.get("input_port")
                self._event("run_ready", run_directory=str(self.run_directory))
                if not self.stop_event.is_set():
                    self.status.set("QNX is starting… Waiting for the first frame.")
            elif kind == "controller":
                self._handle_controller_event(data)
            elif kind == "done":
                self.worker_result = data
                self.worker_finished = True
                self.proof["cleanup_completed"] = True
                self._event("vm_finished", stop_reason=data.get("stop_reason"))
                self.stop_button.configure(state="disabled")
                self._set_controls_enabled(False)
                hmi = data.get("hmi", {})
                if hmi.get("crash_signal"):
                    self.status.set(f"HMI stopped: {hmi['crash_signal']} at {hmi.get('crash_ip')}. Logs have been saved.")
                elif not self.close_requested:
                    self.status.set("Emulator stopped. The last frame remains displayed.")
                self._write_verification()
            elif kind == "error":
                self.worker_error = data["error"]
                self.worker_finished = True
                self.proof["cleanup_completed"] = True
                self.stop_button.configure(state="disabled")
                self._set_controls_enabled(False)
                self.status.set("Startup failed. Details: " + str(self.proof_directory / "worker-error.txt"))
                self._event("worker_error", error=data["error"])
                self._write_verification()
            elif kind == 'extension_ready':
                if self.active_extension == data[0]:
                    self.extension_surface = data[1]
                    self.status.set(data[0].replace('_', ' ').title() + ' · Back returns to iDrive')
                else:
                    threading.Thread(target=data[1].close, daemon=True).start()
            elif kind == 'extension_error':
                self.status.set(str(data))
                self._event('extension_error', detail=str(data))

    def _activate_extension(self, kind):
        if kind not in ('android_auto', 'carplay', 'navigation', 'bluetooth'):
            return
        self._close_extension()
        self.active_extension = kind
        self._publish_extension_state(False)
        self.image_label.configure(image='', text='Starting ' + kind.replace('_', ' ').title() + '…')
        self._event('native_extension_selected', source=kind)
        def start():
            try:
                if kind == 'carplay':
                    from projection_bridge import ProjectionBridge
                    surface = ProjectionBridge()
                    state = surface.status('carplay', refresh=True)
                    if not state['available']:
                        raise RuntimeError(state['message'])
                elif kind == 'navigation':
                    from navigation_surface import NavigationSurface
                    surface = NavigationSurface()
                elif kind == 'bluetooth':
                    from bluetooth_surface import BluetoothSurface
                    surface = BluetoothSurface()
                else:
                    from android_surface import AndroidSurface
                    surface = AndroidSurface()
                    surface.start()
                self.messages.put(('extension_ready', (kind, surface)))
            except Exception as error:
                self.messages.put(('extension_error', str(error)))
        threading.Thread(target=start, daemon=True).start()

    def _close_extension(self):
        surface = self.extension_surface
        self.active_extension = None
        self._publish_extension_state(False)
        self.extension_surface = None
        self.extension_frame = None
        self.extension_photo = None
        self.last_frame_stamp = None
        self._extension_digest = None
        if surface:
            threading.Thread(target=surface.close, daemon=True).start()

    def _publish_extension_state(self, ready):
        if self.run_directory:
            try:
                path=self.run_directory/'extension-state.json'
                temporary=path.with_suffix('.tmp')
                temporary.write_text(json.dumps({'active':self.active_extension,'ready':ready}),encoding='utf-8')
                temporary.replace(path)
            except OSError:
                pass

    def _navigation_destination(self):
        from tkinter import simpledialog
        value = simpledialog.askstring('Navigation destination', 'Destination latitude, longitude (example: 44.4377, 26.0974)', parent=self.root)
        if value and self.extension_surface:
            try:
                latitude, longitude = map(float, value.split(','))
                self.extension_surface.configure(destination=(latitude, longitude))
            except ValueError as error:
                self.status.set('Invalid destination: ' + str(error))

    def _load_extension_frame(self):
        if not self.active_extension or not self.extension_surface:
            return
        frame = self.extension_frame
        if frame and frame[0] == self.active_extension:
            digest = hashlib.sha256(frame[1]).hexdigest()
            if digest != getattr(self, '_extension_digest', None):
                self._extension_digest = digest
                photo = tk.PhotoImage(master=self.root, data=frame[1], format='PPM')
                divisor = max(1, math.ceil(photo.width()/self.max_frame_width), math.ceil(photo.height()/self.max_frame_height))
                self.extension_photo = photo if divisor == 1 else photo.subsample(divisor, divisor)
                self.image_label.configure(image=self.extension_photo, text='')
                if self.run_directory:
                    try:
                        frame_path=self.run_directory/'extension-frame.ppm'
                        temporary=frame_path.with_suffix('.tmp')
                        temporary.write_bytes(frame[1])
                        temporary.replace(frame_path)
                        self._publish_extension_state(True)
                    except OSError:
                        pass
                self.proof['native_extension_displayed'] = self.active_extension
                if self.proof.get('native_extension_first_frame') != self.active_extension:
                    (self.proof_directory / (self.active_extension + '-first-frame.ppm')).write_bytes(frame[1])
                    self.proof['native_extension_first_frame'] = self.active_extension
                    self._event('native_extension_frame_displayed', source=self.active_extension)
                    self._write_verification()
        if self.extension_loading or time.monotonic()-self.extension_last_poll < .07:
            return
        self.extension_loading = True
        self.extension_last_poll = time.monotonic()
        kind, surface = self.active_extension, self.extension_surface
        def fetch():
            try:
                if kind == 'carplay':
                    from PIL import Image
                    encoded = surface.frame('carplay')
                    output = io.BytesIO()
                    with Image.open(io.BytesIO(encoded)) as image:
                        image.convert('RGB').save(output, format='PPM')
                    payload = output.getvalue()
                else:
                    if kind == 'navigation':
                        now = time.monotonic()
                        elapsed = min(1, now-getattr(self, '_navigation_tick', now))
                        self._navigation_tick = now
                        try:
                            telemetry_path = HERE / 'vehicle-state.json'
                            telemetry = json.loads(telemetry_path.read_text(encoding='utf-8'))
                            speed = telemetry.get('speed_kph', 0) if time.time()-telemetry_path.stat().st_mtime < 3 else 0
                            surface.advance(elapsed, float(speed))
                        except (OSError, ValueError, TypeError):
                            pass
                    payload = surface.frame()
                if payload and self.active_extension == kind and self.extension_surface is surface:
                    self.extension_frame = kind, payload
            except Exception as error:
                self.messages.put(('extension_error', str(error)))
            finally:
                self.extension_loading = False
        threading.Thread(target=fetch, daemon=True).start()

    def _load_actual_frame(self):
        if self.active_extension:
            return
        if self.run_directory is None:
            return
        if not self.presentations_seen:
            log = self.run_directory / "relay/renderer-stderr.log"
            try:
                text = log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return
            if not re.search(r"glhost:\s+[1-9]\d*\s+frames swapped", text):
                return
            self.presentations_seen = True
            self.proof["renderer_presentation_seen_before_first_display"] = True
            self._event("renderer_presentation_observed")
        path = self.run_directory / "frame.ppm"
        try:
            info = path.stat()
            stamp = (info.st_mtime_ns, info.st_size)
            if stamp == self.last_frame_stamp:
                return
            payload = path.read_bytes()
            header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255[ \t]*\r?\n", payload[:128])
            if not header:
                return
            width, height = map(int, header.groups())
            if len(payload) != header.end() + width * height * 3:
                return
            if self.startup_active:
                if not self._frame_has_content(payload, header.end()):
                    self.last_frame_stamp = stamp
                    return
                self.startup_active = False
                self._event("startup_screen_replaced_by_hmi")
            if self.full_photo is not None and self.full_photo.width()==width and self.full_photo.height()==height:
                photo = self.full_photo
                photo.configure(data=payload, format="PPM")
            else:
                photo = tk.PhotoImage(master=self.root, data=payload, format="PPM")
            divisor = max(1, math.ceil(width / self.max_frame_width),
                          math.ceil(height / self.max_frame_height))
            displayed = photo if divisor == 1 else photo.subsample(divisor, divisor)
            if displayed is not self.display_photo:
                self.image_label.configure(image=displayed, text="")
            self.full_photo, self.display_photo = photo, displayed
            self.root.update_idletasks()
            self.last_frame_stamp = stamp
            self.frame_loads += 1
            self.proof["last_frame_dimensions"] = [width, height]
            self.proof["last_display_dimensions"] = [displayed.width(), displayed.height()]
            self.proof["last_subsample_divisor"] = divisor
            self.proof["last_display_source_sha256"] = hashlib.sha256(payload).hexdigest()
            self.proof["last_display_widget_mapped"] = bool(self.image_label.winfo_ismapped())
            if self.first_frame_time is None:
                self.first_frame_time = time.monotonic()
                first_path = self.proof_directory / "first-displayed-frame.ppm"
                first_path.write_bytes(payload)
                self.proof.update(actual_frame_displayed=True,
                                  first_frame_path=str(first_path),
                                  first_frame_source_sha256=hashlib.sha256(payload).hexdigest(),
                                  first_frame_dimensions=[width, height])
                self._event("actual_frame_displayed", dimensions=[width, height],
                            display_dimensions=[displayed.width(), displayed.height()])
                self._write_verification()
            if not self.stop_event.is_set() and not self.worker_finished:
                self.status.set(f"Live · original frame {width} × {height} · Stop or close the window to stop.")
        except (OSError, ValueError, tk.TclError):
            # A renderer replaces its current frame atomically. Keep the last
            # valid image if file replacement or decoding overlaps this poll.
            return

    def request_stop(self):
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self._close_extension()
        self.stop_button.configure(state="disabled")
        self._set_controls_enabled(False)
        self.controller_note.set("Closing the keyboard connection…")
        self.status.set("Stopping the emulator and its processes…")
        self._event("stop_requested")

    def request_close(self, reason):
        if self.close_requested:
            return
        self.close_requested = True
        self.close_reason = reason
        self._event("close_requested", reason=reason)
        self.request_stop()

    def _write_verification(self):
        self.proof.update(updated_utc=utc_now(), frame_loads=self.frame_loads,
                          worker_finished=self.worker_finished,
                          worker_error=self.worker_error,
                          controller_cleanup_completed=self.controller_cleanup_completed,
                          stop_requested=self.stop_event.is_set(),
                          close_requested=self.close_requested,
                          close_reason=self.close_reason)
        if self.worker_result is not None:
            self.proof["hmi"] = self.worker_result.get("hmi")
            self.proof["runner_stop_reason"] = self.worker_result.get("stop_reason")
            self.proof["renderer_presentations"] = self.worker_result.get("graphics", {}).get("host_reported_presentations")
            self.proof["source_ifs_sha256"] = self.worker_result.get("image", {}).get("source_sha256")
            self.proof["runner_result"] = str(self.run_directory / "result.json") if self.run_directory else None
        hmi_crash = bool((self.worker_result or {}).get("hmi", {}).get("crash_signal"))
        if self.smoke_seconds is not None and self.worker_finished:
            self.proof["smoke_passed"] = bool(
                self.proof["actual_frame_displayed"] and
                self.proof.get("renderer_presentation_seen_before_first_display") and
                self.proof.get("last_display_widget_mapped") and
                self.proof["cleanup_completed"] and not self.worker_error and
                self.controller_cleanup_completed and
                not hmi_crash and self.close_reason == "smoke_after_frame")
        (self.proof_directory / "verification.json").write_text(
            json.dumps(self.proof, ensure_ascii=False, indent=2), encoding="utf-8")

    def _poll(self):
        self._poll_messages()
        self._load_extension_frame()
        self._load_actual_frame()
        if self.worker_finished and not self.worker.is_alive():
            instance = getattr(self, '_instance_socket', None)
            if instance is not None:
                instance.close()
                self._instance_socket = None
        if self.smoke_seconds is not None:
            if (self.first_frame_time is not None and not self.close_requested and
                    time.monotonic() - self.first_frame_time >= self.smoke_seconds):
                self.request_close("smoke_after_frame")
            elif self.first_frame_time is None and time.monotonic() - self.started >= 180:
                self.request_close("smoke_no_frame_timeout")
            elif self.worker_finished and not self.close_requested:
                self.request_close("smoke_worker_finished_before_close")
        if self.close_requested and self.worker_finished and not self.worker.is_alive():
            self._write_verification()
            self.root.destroy()
            return
        self.root.after(self.poll_ms, self._poll)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", type=float, metavar="SECONDS",
                        help="Close cleanly this many seconds after displaying an actual renderer frame")
    parser.add_argument('--software', action='store_true', help='Use the previous TCG compatibility profile')
    parser.add_argument('--previous', action='store_true', help='Use the previous WHPX socket profile')
    parser.add_argument('--fast', action='store_true',
                        help='Previous default DMA image with the faster legacy renderer (nbt-glhost-dma-fast.exe)')
    parser.add_argument('--legacy', action='store_true',
                        help='Previous default DMA profile (qemu-mhi2-derived bridge, nbt-glhost-dma.exe)')
    parser.add_argument('--native', action='store_true', help='Use the experimental native menu and sport-gauge profile')
    parser.add_argument('--original', action='store_true', help='Use the original profile without integrated features')
    args = parser.parse_args()
    if not any((args.original,args.software,args.previous,args.fast,args.legacy,args.native)):
        args.native = NATIVE_IFS.exists()
    # Hold the launch guard only while this viewer owns an active VM.
    # Diagnostic smoke runs remain independently runnable.
    instance = None
    if args.smoke_test is None:
        from webui import current
        if current()[0]:
            return
        instance = socket.socket()
        try:
            instance.bind(('127.0.0.1', 8878))
        except OSError:
            instance.close()
            return
    if args.smoke_test is not None and not 0 < args.smoke_test <= 300:
        parser.error("--smoke-test requires a duration above 0 and at most 300 seconds")
    if sum(map(bool, (args.original,args.software, args.previous, args.fast, args.legacy, args.native))) > 1:
        parser.error("choose at most one of --software, --previous, --fast, --legacy")
    if not any((args.software, args.previous, args.fast, args.legacy)):
        missing = [p for p in DEFAULT_PROFILE_FILES if not (p.is_dir() and any(p.iterdir()) if p.suffix == ""
                                                             else p.is_file())]
        if missing:
            # RUN_NBT.cmd starts the viewer without a console: report in a window too.
            text = ("Required default profile files are missing (firmware or tools):\n\n" +
                    "\n".join(str(p.relative_to(WORKSPACE)) for p in missing) +
                    "\n\nSee the Firmware section in README.md.")
            print(text, file=sys.stderr)
            try:
                from tkinter import messagebox
                hidden = tk.Tk()
                hidden.withdraw()
                messagebox.showerror("NBT emulator", text)
                hidden.destroy()
            except tk.TclError:
                pass
            raise SystemExit(2)
    root = tk.Tk()
    app = LiveViewer(root, args.smoke_test, args.software, args.previous, args.fast, args.legacy, args.native)
    app._instance_socket = instance
    try:
        root.mainloop()
    except KeyboardInterrupt:
        app.request_close("keyboard_interrupt")
        root.mainloop()
    finally:
        if instance is not None:
            instance.close()
        app.stop_event.set()
        if app.worker and app.worker.is_alive():
            app.worker.join(20)
        app.proof["cleanup_completed"] = bool(app.worker_finished and not app.worker.is_alive())
        app._write_verification()
    if args.smoke_test is not None:
        print("Viewer smoke passed: " + str(app.proof.get("smoke_passed", False)), flush=True)
        print("Verification: " + str(app.proof_directory / "verification.json"), flush=True)
        if not app.proof.get("smoke_passed"):
            raise SystemExit(2)


if __name__ == "__main__":
    import struct
    if struct.calcsize('P') == 4:
        from webui import viewer_python
        native_python = viewer_python()
        if native_python != Path(sys.executable):
            import subprocess
            raise SystemExit(subprocess.call(
                [str(native_python), str(Path(__file__).resolve()), *sys.argv[1:]],
                creationflags=subprocess.CREATE_NO_WINDOW))
    main()
