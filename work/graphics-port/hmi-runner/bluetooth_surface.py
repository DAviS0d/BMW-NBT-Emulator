"""Bluetooth device-selection surface backed by the real Windows radio."""
import io
import queue
import threading
from PIL import Image, ImageDraw, ImageFont
from bluetooth_bridge import BluetoothBridge


class BluetoothSurface:
    def __init__(self):
        self.bridge = BluetoothBridge()
        self.devices = {}
        self.selected = 0
        self.pending_pair = None
        self.lock = threading.RLock()
        self.message = self.bridge.status()['message']
        if self.bridge.status()['radio_present']:
            self.bridge.start()
            self.message = 'Starting Windows Bluetooth…'
        try:
            self.font = ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf', 24)
        except OSError:
            self.font = ImageFont.load_default()

    def _events(self):
        while True:
            try:
                item = self.bridge.events.get_nowait()
            except queue.Empty:
                return
            kind = item.get('ev')
            if kind == 'ready':
                self.bridge.send({'cmd':'paired'})
                self.message = 'Paired devices · OPTION scans for phones'
            elif kind == 'device':
                self.devices[item['addr']] = item
            elif kind == 'scan_end':
                self.message = 'Scan complete. Select a phone to pair or connect.'
            elif kind == 'passkey':
                self.pending_pair = item
                self.message = f"Confirm {item.get('value', '')} on your phone, then press OK."
            elif kind == 'pair_result':
                self.pending_pair = None
                self.message = 'Pairing succeeded' if item.get('ok') else 'Pairing failed or was rejected'
                self.bridge.send({'cmd':'paired'})
            elif kind == 'connected':
                self.message = 'Bluetooth audio connected' if item.get('ok') else str(item.get('why', 'Connection failed'))
            elif kind == 'track':
                self.message = str(item.get('artist', '')) + ' · ' + str(item.get('title', ''))
            elif kind == 'unavailable':
                self.message = 'Windows Bluetooth transport unavailable'

    def action(self, name):
        with self.lock:
            self._events()
            if name in ('up', 'down'):
                self.selected = min(max(0, len(self.devices)-1), max(0, self.selected + (-1 if name == 'up' else 1)))
            elif name == 'option':
                self.bridge.send({'cmd':'scan','seconds':10})
                self.message = 'Scanning for phones…'
            elif name == 'select':
                if self.pending_pair:
                    self.bridge.send({'cmd':'passkey_reply','accept':True})
                elif self.devices:
                    device = list(self.devices.values())[self.selected]
                    self.bridge.send({'cmd':'connect' if device.get('paired') else 'pair','addr':device['addr']})
                    self.message = 'Connecting…' if device.get('paired') else 'Pairing…'
            elif name in ('tilt_left','tilt_right'):
                self.bridge.send({'cmd':'control','what':'previous' if name == 'tilt_left' else 'next'})

    def frame(self):
        with self.lock:
            self._events()
            image = Image.new('RGB', (1280,480), '#080c12')
            draw = ImageDraw.Draw(image)
            draw.text((45,25), 'Bluetooth · PC radio', font=self.font, fill='#ffbd7b')
            draw.line((40,70,1200,70), fill='#e85c20', width=2)
            for i, device in enumerate(list(self.devices.values())[:7]):
                y = 100+i*42
                if i == self.selected:
                    draw.rectangle((45,y-3,700,y+35), fill='#a43209')
                draw.text((60,y), device.get('name',device['addr']) + (' · paired' if device.get('paired') else ''), font=self.font, fill='white')
            if not self.devices:
                draw.text((55,115), 'No Bluetooth phones available', font=self.font, fill='#d3dbe5')
            draw.text((45,385), self.message[:95], font=self.font, fill='#d3dbe5')
            draw.text((45,435), 'OK: pair/connect   OPTION: scan   BACK: iDrive   A2DP audio / media controls', font=self.font, fill='#7d98b1')
            output = io.BytesIO()
            image.save(output, format='PPM')
            return output.getvalue()

    def close(self):
        self.bridge.close()
