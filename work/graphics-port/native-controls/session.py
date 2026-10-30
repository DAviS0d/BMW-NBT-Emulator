# © 2026 davisod & JEtsKi
"""Host controller session: original MTP packets over VM COM2, no HMI patches."""
import json
import queue
import re
import select
import socket
import struct
import threading
import time
from pathlib import Path
from native_controls import (NativeCcsPeripheral, MtpPacket, MtpStream, ControlsNotReady,
                             hmi_target_from_registry)

# Original HMI controller key codes posted to the native keyboard queue.
# Evidence: work/graphics-port/host/input-audit/BUTTONS.md (mapper 0x08097306,
# processHardKey 0x081a4e14, KEY_NORTH/SOUTH/WEST/EAST switch 0x08488bf3).
KEYBOARD_KEYS = {'menu': 1, 'back': 2, 'option': 3, 'select': 8, 'down': 13, 'up': 14,
                 'tilt_up': 9, 'tilt_down': 10, 'tilt_left': 11, 'tilt_right': 12,
                 'media': 4, 'radio': 5, 'tel': 6, 'nav': 7}
ROTARY_KEYS = (13, 14)


class NativeInputSession:
    def __init__(self, info, stop_event, on_event=None, rotary_version=1,
                 button_hold_seconds=.075, button_release_gap_seconds=.075,
                 extra_peripherals=(), doom_extension=False, native_extension=False):
        self.folder = Path(info['run_directory'])
        self.port = info['input_port']
        self.fast_transport = info.get('input_kind') == 'virtio'
        self.keyboard_hal = bool(info.get('keyboard_hal'))
        self.stop_event = stop_event
        self.on_event = on_event or (lambda item: None)
        self.extra_peripherals = tuple(extra_peripherals)
        self.doom_extension = bool(doom_extension)
        self.native_extension = bool(native_extension)
        self.rotary_version = rotary_version
        if not 0 <= button_hold_seconds <= 1 or not 0 <= button_release_gap_seconds <= 1:
            raise ValueError('Button timing must be between0 and1second')
        self.button_hold_seconds = button_hold_seconds
        self.button_release_gap_seconds = button_release_gap_seconds
        self.actions = queue.Queue()
        self.peripheral = None
        self.ready = False
        self.configuration_count = 0
        self.connected = False
        self.thread = threading.Thread(target=self._run, name='native-idrive', daemon=True)

    def start(self):
        self.thread.start()

    def action(self, name):
        self.actions.put(name)

    def join(self, timeout=3):
        self.thread.join(timeout)

    def _run(self):
        started = time.monotonic()
        connection = None
        log_path = self.folder / 'controller-events.jsonl'
        log = log_path.open('w', encoding='utf-8')
        mailbox = None
        if self.native_extension:
            from native_mailbox import NativeMailbox
            mailbox = NativeMailbox(self.folder)
        def event(kind, **fields):
            item = {'kind': kind, 'seconds': round(time.monotonic()-started, 3), **fields}
            log.write(json.dumps(item) + '\n')
            log.flush()
            self.on_event(item)

        def send(packet, label):
            # Pace the small hardware-control stream below the UART FIFO rate.
            if self.fast_transport:
                connection.sendall(packet)
            else:
                for byte in packet:
                    if self.stop_event.is_set():
                        return
                    connection.sendall(bytes([byte]))
                    time.sleep(.001)
            event('native_input_sent', label=label, hex=packet.hex(' '))

        def discover_target(target, source):
            self.peripheral = NativeCcsPeripheral(target,
                rotary_status_version=self.rotary_version, menu_button=(0, 1))
            event('native_hmi_target', target=f'{target:04x}', source=source)

        try:
            while not self.stop_event.is_set():
                try:
                    connection = socket.create_connection(('127.0.0.1', self.port), timeout=.5)
                    break
                except OSError:
                    self.stop_event.wait(.05)
            if connection is None:
                return
            connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            connection.settimeout(.5)
            self.connected = True
            event('input_transport_connected')
            stream = MtpStream()
            advertised = False
            last_probe = 0
            last_monitor_publish = 0
            last_serial = ''
            serial_offset = 0
            transport_ready = False
            last_serial_check = 0
            control_file = self.folder / 'controller-actions.jsonl'
            control_file.touch()
            file_offset = 0
            last_sports_send = 0
            sports_sequence = 0
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now-last_serial_check >= .1 and (not transport_ready or self.peripheral is None):
                    last_serial_check = now
                    serial_path = self.folder / 'serial_com1.log'
                    if serial_path.exists():
                        with serial_path.open('rb') as serial:
                            serial.seek(serial_offset)
                            block = serial.read()
                            serial_offset += len(block)
                        last_serial += block.decode('utf-8', errors='replace')
                    if self.peripheral is None and now-started >= 10:
                        match = re.search(r'ResponseMOSTClient\(\) : \(clientID, deviceID\)=\(0x[0-9a-fA-F]+, 0x([0-9a-fA-F]+)\)', last_serial)
                        if match:
                            discover_target(int(match.group(1), 16), 'diagnostic_log_fallback')
                    transport_ready = ('NBT_MTP_VIRTIO_BIDIRECTIONAL_READY' in last_serial if self.fast_transport
                                       else 'READY_MIN7_MAX4096' in last_serial)
                if self.peripheral is not None and not advertised and transport_ready:
                    renderer = self.folder / 'relay/renderer-stderr.log'
                    if renderer.exists() and 'frames swapped' in renderer.read_text(errors='replace'):
                        registrations = self.peripheral.register_frames()
                        if self.keyboard_hal:
                            registrations = registrations[-1:]
                        for peripheral in self.extra_peripherals:
                            registrations += peripheral.register_frames()
                        for packet in registrations:
                            send(packet, 'advertise_native_device')
                            self.stop_event.wait(.1)
                        self.stop_event.wait(.3)
                        # UserMonitorControl enables the native display/input path.
                        # Keyboard input has its own original queue, so the display
                        # is advertised independently of physical CCS timing.
                        initial_status = (self.peripheral.power_status() if self.keyboard_hal
                                          else self.peripheral.reset_and_power())
                        initial_status += self.peripheral.monitor_status()
                        for packet in initial_status:
                            send(packet, 'native_readiness_and_power')
                        last_monitor_publish = time.monotonic()
                        advertised = True
                        event('native_devices_advertised')
                if self.keyboard_hal and advertised and not self.ready and now-last_probe >= .5:
                    send(struct.pack('>HBBBBH', 8, 0xfe, 1, 0, 0, 0), 'query_original_input_queue')
                    last_probe = time.monotonic()

                readable, _, _ = select.select([connection], [], [], .01)
                if readable:
                    block = connection.recv(65536)
                    if not block:
                        event('transport_closed')
                        break
                    replies = []
                    latest_ack = None
                    for packet in stream.feed(block):
                        parsed = MtpPacket.parse(packet)
                        event('native_packet_received', hex=packet.hex(' '))
                        if self.native_extension and parsed.type == 0xfb and len(packet) == 8:
                            identifier = int.from_bytes(packet[4:6], 'big')
                            if identifier in (4, 12, 13, 14):
                                event('native_device_selected', item_id=identifier,
                                      source={4:'bluetooth',12:'android_auto',13:'carplay',14:'navigation'}[identifier])
                            continue
                        if self.native_extension and parsed.type == 0xf9 and len(packet) == 8:
                            event('native_sports_ack', power_percent=packet[4], torque_percent=packet[5],
                                  sequence=int.from_bytes(packet[6:8], 'big'))
                            continue
                        if self.peripheral is None:
                            target = hmi_target_from_registry(packet)
                            if target is not None:
                                discover_target(target, 'original_mtp_registry')
                        if self.keyboard_hal and parsed.type == 0xfd and len(packet) == 8:
                            if packet[4] == 0:
                                if packet[5] == 1 and not self.ready:
                                    self.ready = True
                                    event('controller_configured', backend='original_native_keyboard_queue')
                                elif packet[5] == 0 and not self.ready and time.monotonic()-last_monitor_publish >= 1:
                                    # Reannounce the actual virtual monitor state
                                    # until the native display subscriber exists.
                                    for status in self.peripheral.monitor_status(self.peripheral.monitor_enabled):
                                        send(status, 'native_monitor_initialization_retry')
                                    last_monitor_publish = time.monotonic()
                            else:
                                event('native_queue_event_posted', key=packet[4], pressed=packet[5],
                                      repeat=int.from_bytes(packet[6:8], 'big'))
                            continue
                        if self.peripheral is None:
                            continue
                        for reply in self.peripheral.on_native_packet(packet):
                            response = MtpPacket.parse(reply)
                            if response.fblock == 0xe5 and response.function == 0xc30:
                                latest_ack = reply
                                self.configuration_count += 1
                                event('native_configuration', configuration=self.peripheral.last_event)
                            else:
                                replies.append(reply)
                        for peripheral in self.extra_peripherals:
                            for reply in peripheral.on_native_packet(packet, self.peripheral.target):
                                replies.append(reply)
                    if latest_ack is not None:
                        send(latest_ack, 'ack_actual_native_configuration')
                        if not self.ready and not self.keyboard_hal:
                            self.ready = True
                            event('controller_configured', handle=self.peripheral.configuration.handle)
                    for reply in replies:
                        send(reply, 'native_property_response')

                if self.native_extension and self.ready and transport_ready and now - last_sports_send >= .1:
                    state_path = Path(__file__).resolve().parents[1] / 'hmi-runner/vehicle-state.json'
                    try:
                        state = json.loads(state_path.read_text(encoding='utf-8'))
                        power = min(100, max(0, round(float(state.get('power_kw', 0)) / 400 * 100)))
                        torque = min(100, max(0, round(float(state.get('torque_nm', 0)) / 800 * 100)))
                    except (OSError, ValueError, TypeError):
                        power = torque = 0
                    sports_sequence = (sports_sequence + 1) & 0xffff
                    try:
                        selected,applied=mailbox.exchange(power,torque)
                        if selected in (4,12,13,14):
                            event('native_device_selected', item_id=selected,
                                  source={4:'bluetooth',12:'android_auto',13:'carplay',14:'navigation'}[selected])
                        if applied is not None:
                            event('native_sports_ack',power_percent=power,torque_percent=torque,sequence=applied,transport='owned_guest_mailbox')
                    except OSError as error:
                        event('native_mailbox_error',error=str(error))
                        mailbox.close()
                    last_sports_send = now

                try:
                    with control_file.open('rb') as source:
                        source.seek(file_offset)
                        control_lines = source.readlines()
                except PermissionError:
                    # A Windows writer can briefly deny sharing. Retry the same
                    # offset; a transient file lock must not drop native input.
                    control_lines = []
                for line in control_lines:
                    if not line.endswith(b'\n'):
                        break
                    file_offset += len(line)
                    if line.strip():
                        action = json.loads(line)['action']
                        if action == 'stop':
                            event('stop_requested_by_controller_client')
                            self.stop_event.set()
                            return
                        self.actions.put(action)
                if self.ready:
                    try:
                        action = self.actions.get_nowait()
                    except queue.Empty:
                        continue
                    try:
                        if action == 'stop':
                            event('stop_requested_by_controller_client')
                            self.stop_event.set()
                            continue
                        if self.native_extension and action in KEYBOARD_KEYS:
                            try:
                                extension=json.loads((self.folder/'extension-state.json').read_text(encoding='utf-8'))
                            except (OSError,ValueError):
                                extension={}
                            if extension.get('active'):
                                event('extension_action',action=action)
                                continue
                        if self.native_extension and action.startswith('sports:'):
                            _, power, torque = action.split(':')
                            power, torque = int(power), int(torque)
                            if not 0 <= power <= 100 or not 0 <= torque <= 100:
                                raise ValueError('Sports percentages must be 0..100')
                            mailbox.exchange(power,torque)
                            continue
                        # Explicit device bring-up commands for bounded protocol
                        # diagnostics. They use the same original MTP framing.
                        if action in ('advertise_physical_ccs', 'advertise_virtual_ccs',
                                      'reset_ccs', 'monitor_on', 'power_on'):
                            if action == 'advertise_physical_ccs':
                                packets = self.peripheral.register_frames()[:1]
                            elif action == 'advertise_virtual_ccs':
                                packets = self.peripheral.register_frames()[1:2]
                            elif action == 'reset_ccs':
                                packets = self.peripheral.reset()
                            elif action == 'monitor_on':
                                packets = self.peripheral.monitor_status()
                            else:
                                packets = self.peripheral.power_status()
                            for packet in packets:
                                send(packet, action)
                            event('device_bringup_sent', action=action)
                            continue
                        if self.keyboard_hal and self.doom_extension and action.startswith('doom:'):
                            fields = action.split(':')
                            if len(fields) != 3:
                                raise ValueError('Doom action requires code and pressed state')
                            code, pressed = map(int, fields[1:])
                            if not 0 <= code <= 0x101 or pressed not in (0, 1):
                                raise ValueError('Invalid Doom key packet')
                            send(struct.pack('>HBBHBB', 8, 0xfc, 1, code, pressed, 0), action)
                            event('action_sent', action=action, backend='QNX_Doom_extension')
                            continue
                        if self.keyboard_hal and (action in KEYBOARD_KEYS or action.startswith('key:')):
                            if self.native_extension and action == 'nav':
                                event('native_device_selected', item_id=14, source='navigation')
                            if action in KEYBOARD_KEYS:
                                key = KEYBOARD_KEYS[action]
                            else:
                                # Diagnostic raw push code, same range the guest HAL accepts.
                                key = int(action[4:])
                                if not 1 <= key <= 12:
                                    raise ValueError('Raw key action requires a push code 1..12')
                            packets = ([struct.pack('>HBBBBH', 8, 0xfe, 1, key, 0, 1)] if key in ROTARY_KEYS else
                                       [struct.pack('>HBBBBH', 8, 0xfe, 1, key, pressed, 0) for pressed in (1, 0)])
                            for packet in packets:
                                send(packet, action)
                                delay = (.075 if key in ROTARY_KEYS else
                                         self.button_hold_seconds if packet[5] else
                                         self.button_release_gap_seconds)
                                self.stop_event.wait(delay)
                            event('action_sent', action=action, key=key, backend='original_native_keyboard_queue',
                                  button_hold_seconds=self.button_hold_seconds if key not in ROTARY_KEYS else None)
                            continue
                        if action in ('route0', 'route1'):
                            self.peripheral.tx_type = int(action[-1])
                            event('native_tx_type_selected', tx_type=self.peripheral.tx_type)
                            continue
                        if action in ('up', 'down'):
                            packets = self.peripheral.rotate(-1 if action == 'up' else 1)
                        elif action in ('version1', 'version2'):
                            self.peripheral.rotary_status_version = int(action[-1])
                            event('rotary_layout_selected', version=int(action[-1]))
                            continue
                        else:
                            packets = self.peripheral.click(action)
                        for packet in packets:
                            send(packet, action)
                            self.stop_event.wait(.075)
                        event('action_sent', action=action,
                              handle=self.peripheral.configuration.handle,
                              position=self.peripheral.position)
                    except (ControlsNotReady, ValueError, OSError) as error:
                        event('action_rejected', action=action, error=str(error))
        except (OSError, ValueError) as error:
            event('input_session_ended', error=repr(error))
        finally:
            self.connected = self.ready = False
            if mailbox is not None:
                mailbox.close()
            if connection:
                connection.close()
            event('input_session_closed')
            log.close()
