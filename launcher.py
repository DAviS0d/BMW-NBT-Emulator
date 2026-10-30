"""Desktop launcher for BMW NBT and its local tools. No extra packages required."""
import argparse
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / 'work/graphics-port/hmi-runner'
sys.path.insert(0, str(RUNNER))
import webui


class Launcher:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.python = webui.viewer_python()
        self.simulator = None
        self.starting = 0
        self.viewer_process = None
        self.logs = ROOT / 'outputs/NBT_launcher'
        self.logs.mkdir(parents=True, exist_ok=True)
        root.title('BMW NBT Launcher')
        root.geometry('850x680')
        root.minsize(760, 620)
        root.configure(bg='#0b1017')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TButton', font=('Segoe UI', 11), padding=13,
                        background='#1c2d42', foreground='#eef4ff', borderwidth=0)
        style.map('TButton', background=[('active', '#315474'), ('disabled', '#172332')],
                  foreground=[('disabled', '#718399')])
        self.label('BMW NBT', 27, '#eef4ff').pack(anchor='w', padx=28, pady=(25, 4))
        self.label('ORIGINAL FIRMWARE  /  LOCAL CONTROL CENTER', 9, '#7f9fbe').pack(anchor='w', padx=30)
        self.state = tk.StringVar(value='Checking emulator…')
        self.detail = tk.StringVar(value='')
        card = tk.Frame(root, bg='#142131', padx=20, pady=16)
        card.pack(fill='x', padx=28, pady=20)
        tk.Label(card, textvariable=self.state, bg='#142131', fg='#eef4ff', font=('Segoe UI', 17)).pack(anchor='w')
        tk.Label(card, textvariable=self.detail, bg='#142131', fg='#9eb2c9', font=('Segoe UI', 10)).pack(anchor='w', pady=(5, 0))
        self.native_profile = tk.BooleanVar(value=(ROOT / 'work/bridge-v2/ifs/walthread_keyboard_dma_v2_native.ifs').exists())
        tk.Checkbutton(card, text='Enable integrated phone, sport and navigation features',
                       variable=self.native_profile, bg='#142131', fg='#eef4ff',
                       selectcolor='#142131', activebackground='#142131',
                       activeforeground='#eef4ff').pack(anchor='w', pady=(9, 0))
        buttons = tk.Frame(root, bg='#0b1017')
        buttons.pack(fill='x', padx=28)
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        self.start_button = self.button(buttons, 'Start BMW emulator', self.start_emulator, 0, 0)
        self.stop_button = self.button(buttons, 'Stop emulator', self.stop_emulator, 0, 1)
        self.button(buttons, 'Open web interface', self.open_web, 1, 0)
        self.diagnostic_button = self.button(buttons, 'Check hypervisor', self.diagnostic, 1, 1)
        self.sim_button = self.button(buttons, 'Run vehicle simulator', self.simulate, 2, 0)
        self.button(buttons, 'Open logs folder', lambda: os.startfile(str(RUNNER / 'viewer-runs')), 2, 1)
        self.label('ACTIVITY', 9, '#8096ae').pack(anchor='w', padx=30, pady=(15, 7))
        self.output = ScrolledText(root, height=9, bg='#080d13', fg='#bbcddd', relief='flat',
                                   font=('Consolas', 9), padx=12, pady=12, state='disabled')
        self.output.pack(fill='both', expand=True, padx=28)
        self.label('Phone connections require compatible hardware. Maps use OpenStreetMap and a simulated GPS position.',
                   9, '#8ea2b8').pack(anchor='w', padx=28, pady=(12, 3))
        self.label('Closing the launcher leaves the emulator running.', 9, '#687f96').pack(anchor='w', padx=28, pady=(0, 18))
        self.append('Ready. Software CPU startup usually takes about 25 seconds.')
        root.after(100, self.poll)

    def label(self, text, size, color):
        return tk.Label(self.root, text=text, bg='#0b1017', fg=color, font=('Segoe UI', size))

    @staticmethod
    def button(parent, text, command, row, column):
        button = ttk.Button(parent, text=text, command=command)
        button.grid(row=row, column=column, sticky='ew', padx=(0, 7) if column == 0 else (7, 0), pady=(0, 9))
        return button

    def append(self, text):
        self.output.configure(state='normal')
        self.output.insert('end', text.rstrip() + '\n')
        self.output.see('end')
        self.output.configure(state='disabled')

    def background(self, script, arguments=()):
        with (self.logs / (script.stem + '-startup.log')).open('a', encoding='utf-8') as output:
            return subprocess.Popen([str(self.python.with_name('pythonw.exe')), str(script),*arguments],
                                    cwd=ROOT, stdout=output, stderr=output,
                                    creationflags=subprocess.CREATE_NO_WINDOW)

    def start_emulator(self):
        try:
            if webui.current()[0]:
                self.append('Emulator already running. Open the web interface to control it.')
                return
            arguments=['--native'] if getattr(self,'native_profile',None) and self.native_profile.get() else ['--original']
            self.viewer_process = self.background(RUNNER / 'viewer.py',arguments)
            self.starting = time.monotonic()
            self.start_button.configure(state='disabled')
            self.append('Starting original BMW firmware…')
        except OSError as error:
            self.append('Startup failed: ' + str(error))

    def stop_emulator(self):
        try:
            webui.action('stop')
            self.append('Emulator stop requested.')
        except (ValueError, OSError) as error:
            self.append(str(error))

    def open_web(self):
        def work():
            url = 'http://127.0.0.1:8877'
            for attempt in range(30):
                try:
                    with urllib.request.urlopen(url + '/api/status', timeout=.5):
                        pass
                    webbrowser.open(url)
                    self.events.put(('text', 'Web interface: ' + url))
                    return
                except OSError:
                    if attempt == 0:
                        try:
                            self.background(RUNNER / 'webui.py')
                        except OSError as error:
                            self.events.put(('text', str(error)))
                            return
                    time.sleep(.2)
            self.events.put(('text', 'Web server startup failed. See outputs/NBT_launcher.'))
        threading.Thread(target=work, daemon=True).start()

    def stream(self, arguments, kind):
        def work():
            try:
                process = subprocess.Popen([str(self.python), '-u', *map(str, arguments)], cwd=ROOT,
                                           stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                self.events.put(('started', (kind, process)))
                for line in process.stdout:
                    if kind == 'simulator':
                        try:
                            state = json.loads(line)
                            line = (f"Vehicle: {state['speed_kph']:.0f} km/h | {state['rpm']:.0f} RPM | "
                                    f"gear {state['gear']} | {state['power_kw']:.0f} kW")
                        except (ValueError, KeyError, TypeError):
                            pass
                    self.events.put(('text', line.rstrip()))
                code = process.wait()
                process.stdout.close()
                self.events.put(('text', f'{kind.capitalize()} finished (exit {code}).'))
            except OSError as error:
                self.events.put(('text', str(error)))
            finally:
                self.events.put(('done', kind))
        threading.Thread(target=work, daemon=True).start()

    def diagnostic(self):
        self.diagnostic_button.configure(state='disabled')
        self.append('Checking Windows hypervisor and testing WHPX…')
        self.stream([ROOT / 'tools/check_hypervisor.py'], 'diagnostic')

    def simulate(self):
        if self.simulator and self.simulator.poll() is None:
            self.simulator.terminate()
            return
        self.sim_button.configure(state='disabled')
        self.append('Starting a 60-second host vehicle-data demo.')
        self.stream([RUNNER / 'vehicle_sim_cli.py', '--demo', '--seconds', '60', '--hz', '1',
                     '--output', RUNNER / 'vehicle-state.json'], 'simulator')

    def poll(self):
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'text':
                self.append(data)
            elif kind == 'started' and data[0] == 'simulator':
                self.simulator = data[1]
                self.sim_button.configure(text='Stop vehicle simulator', state='normal')
            elif kind == 'done':
                if data == 'diagnostic':
                    self.diagnostic_button.configure(state='normal')
                else:
                    self.simulator = None
                    self.sim_button.configure(text='Run vehicle simulator', state='normal')
        try:
            state = webui.status()
            if (self.starting and not state['running'] and self.viewer_process is not None
                    and self.viewer_process.poll() is not None):
                self.append('Viewer exited before the VM started. See outputs/NBT_launcher/viewer-startup.log.')
                self.starting = 0
                self.viewer_process = None
            pending = time.monotonic() - self.starting < 45
            if state['running']:
                self.starting = 0
                self.state.set('Emulator running' if state['frame'] else 'Booting BMW firmware…')
                mode = 'TCG software CPU' if state['accelerator'] == 'tcg' else 'WHPX hardware acceleration'
                self.detail.set(mode + '  ·  ' + ('Controls connected' if state['ready'] else 'Controls initializing'))
            else:
                self.state.set('Starting emulator…' if pending else 'Emulator stopped')
                self.detail.set('Waiting for the VM process' if pending else 'Choose Start BMW emulator to boot')
            self.start_button.configure(state='disabled' if state['running'] or pending else 'normal')
            self.stop_button.configure(state='normal' if state['running'] else 'disabled')
        except OSError as error:
            self.detail.set(str(error))
        self.root.after(500, self.poll)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    for path in (RUNNER / 'viewer.py', RUNNER / 'webui.py', RUNNER / 'vehicle_sim_cli.py', ROOT / 'tools/check_hypervisor.py'):
        if not path.is_file():
            raise SystemExit('Missing launcher component: ' + str(path))
    if args.check:
        print('Desktop launcher components verified.')
        return
    instance = socket.socket()
    try:
        instance.bind(('127.0.0.1', 8879))
    except OSError:
        instance.close()
        return
    root = tk.Tk()
    Launcher(root)
    root.mainloop()
    instance.close()


if __name__ == '__main__':
    main()
