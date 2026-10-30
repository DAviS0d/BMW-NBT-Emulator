# © 2026 davisod & JEtsKi
"""Stateful MOST/MTP CCS peripheral, with no GUI, VM, or HMI callbacks.

All returned bytes go through the original mtp2most/MOST path. No menu state is
invented. The caller owns socket I/O, scheduling and any button-pair delay.
"""
from dataclasses import dataclass
import struct
import threading


class ProtocolError(ValueError):
    pass


class ControlsNotReady(RuntimeError):
    pass


@dataclass(frozen=True)
class MtpPacket:
    raw: bytes
    type: int
    subtype: int
    target: int | None = None
    fblock: int | None = None
    instance: int | None = None
    function: int | None = None
    operation: int | None = None
    tx_type: int | None = None
    payload: bytes = b''

    @classmethod
    def parse(cls, raw):
        raw = bytes(raw)
        if not 4 <= len(raw) <= 4096 or int.from_bytes(raw[:2], 'big') != len(raw):
            raise ProtocolError('MTP requires a matching BE16 total length, 4..4096 bytes')
        if raw[2] != 2:
            return cls(raw, raw[2], raw[3], payload=raw[4:])
        if len(raw) < 12:
            raise ProtocolError('MTP type 2 requires its complete 12-byte header')
        _, typ, subtype, target, fb, inst, fid, op, tx = struct.unpack('>HBBHBBHBB', raw[:12])
        return cls(raw, typ, subtype, target, fb, inst, fid, op, tx, raw[12:])


class MtpStream:
    """Frame fragmented/coalesced native bytes; reject invalid lengths explicitly."""
    def __init__(self):
        self.pending = bytearray()

    def feed(self, data):
        self.pending.extend(data)
        frames = []
        while len(self.pending) >= 2:
            size = int.from_bytes(self.pending[:2], 'big')
            if not 4 <= size <= 4096:
                raise ProtocolError(f'Invalid native MTP total length {size}')
            if len(self.pending) < size:
                break
            raw = bytes(self.pending[:size])
            MtpPacket.parse(raw)
            del self.pending[:size]
            frames.append(raw)
        return frames


def data_frame(target, fblock, instance, function, payload=b'', *, operation=0x0c,
               subtype=0xdb, tx_type=1):
    payload = bytes(payload)
    if not 0 <= target <= 0xffff or not 0 <= function <= 0xffff:
        raise ProtocolError('Target and function must fit u16')
    if any(not 0 <= v <= 0xff for v in (fblock, instance, operation, subtype, tx_type)):
        raise ProtocolError('MTP byte field out of range')
    size = 12 + len(payload)
    if size > 4096:
        raise ProtocolError('MTP frame exceeds the native UART bridge limit')
    return struct.pack('>HBBHBBHBB', size, 2, subtype, target, fblock, instance,
                       function, operation, tx_type) + payload


def register_frames():
    """The three original seven-byte device registrations, in dependency order."""
    return [bytes.fromhex(value) for value in
            ('00 07 01 00 02 e5 01', '00 07 01 00 02 e5 0f', '00 07 01 00 02 d1 02')]


def hmi_target_from_registry(packet):
    """Read the actual HMIControl10/01 owner from an original full MTP registry."""
    msg = MtpPacket.parse(packet)
    if msg.type != 7 or msg.subtype != 1 or len(packet) < 8:
        return None
    count = int.from_bytes(packet[4:6], 'big')
    if packet[6:8] != b'\x00\x00' or len(packet) != 8+count*4:
        return None
    owners = {int.from_bytes(packet[at:at+2], 'big')
              for at in range(8, len(packet), 4)
              if packet[at+2:at+4] == b'\x10\x01'}
    owners.discard(0)
    owners.discard(0xffff)
    return next(iter(owners)) if len(owners) == 1 else None


@dataclass(frozen=True)
class RotaryConfiguration:
    handle: int
    mode: int
    count: int
    start: int
    cluster: int

    @classmethod
    def parse(cls, payload):
        if len(payload) != 9:
            raise ProtocolError('Native c30 SET must contain exactly nine bytes')
        sender, receiver, handle, mode, count, start, cluster = struct.unpack('>BBBBHHB', payload)
        if (sender, receiver) != (29, 1):
            raise ProtocolError('Native c30 SET has unexpected logical sender/receiver')
        if handle in (0, 0xff) or mode > 7 or count > 0xfff or cluster != 0x1e:
            raise ProtocolError('Native c30 SET fields fail the verified central-controller contract')
        if count and start >= count:
            raise ProtocolError('Finite detent configuration starts outside its detents')
        return cls(handle, mode, count, start, cluster)


class NativeCcsPeripheral:
    """Minimal central CCS hardware state tied to real outbound HMI config.

    rotary_status_version is REQUIRED: 1 omits the MODE byte; 2 includes it.
    This chooses payload layout, not a nonexistent MTP header-version field.
    Native parser header+5 is the instance byte: instance1 requires layout1.
    The option keeps its earlier name for API compatibility; it is not a
    firmware/message version selector and does not alter the packet instance.
    """
    BUTTONS = {'select': (0x1e, 1), 'back': (0, 2), 'option': (0, 4),
               'central_key_1': (0, 1)}

    def __init__(self, target, *, rotary_status_version, status_mode=0, subtype=0xdb,
                 menu_button=None, tx_type=1):
        if rotary_status_version not in (1, 2):
            raise ValueError('Choose rotary_status_version=1 or 2 explicitly')
        if not 0 <= status_mode <= 3:
            raise ValueError('Incoming rotary STATUS mode is 0..3')
        if not 0 <= target <= 0xffff or not 0 <= subtype <= 0xff:
            raise ValueError('Invalid MTP target/subtype')
        if menu_button is not None and tuple(menu_button) != (0, 1):
            raise ValueError('Only the verified central_key_1 tuple can be explicitly named menu')
        self.target, self.subtype = target, subtype
        self.tx_type = tx_type
        self.rotary_status_version, self.status_mode = rotary_status_version, status_mode
        self.menu_button = tuple(menu_button) if menu_button is not None else None
        self.configuration = None
        self.position = None
        self.power_raw = 3
        self.monitor_enabled = True
        self.pressed = set()
        self.last_event = None
        self._lock = threading.RLock()

    def register_frames(self):
        return register_frames()

    def _status(self, fb, inst, fid, payload):
        return data_frame(self.target, fb, inst, fid, payload, subtype=self.subtype, tx_type=self.tx_type)

    def readiness_frame(self):
        return self._status(0xe5, 0x0f, 0xc06, bytes((1, 29, 0, 6)))

    def reset(self):
        """Hardware reset status; await a fresh real c30 SET before controls."""
        with self._lock:
            self.configuration = self.position = None
            self.pressed.clear()
            return [self.readiness_frame()]

    def power_status(self, raw=3):
        with self._lock:
            if not 0 <= raw <= 16:
                raise ValueError('Native power property accepts raw states 0..16')
            self.power_raw = raw
            return [self._status(0xd1, 2, 0x430, bytes((raw,)))]

    def reset_and_power(self):
        with self._lock:
            return self.reset() + self.power_status()

    def monitor_status(self, enabled=True):
        """Original UserMonitorControl STATUS; native display service enables input."""
        if not isinstance(enabled, bool):
            raise ValueError('Monitor state must be a boolean')
        with self._lock:
            self.monitor_enabled = enabled
            return [self._status(0xd1, 2, 0x432, bytes((int(enabled),)))]

    def _configured(self):
        if self.configuration is None:
            raise ControlsNotReady('Awaiting an actual native c30 SET; no handle or position guessed')
        return self.configuration

    def _rotary_status(self, position, overflow=0):
        cfg = self._configured()
        payload = bytes((1, 29, cfg.handle)) + struct.pack('>H', position)
        if self.rotary_status_version != 1:
            payload += bytes((self.status_mode,))
        return self._status(0xe5, 1, 0xc10, payload + bytes((cfg.cluster, overflow)))

    def on_native_packet(self, packet):
        """Consume one complete native MTP frame and return peripheral replies.

        c30 SET/SETGET receives an ACK with that exact handle. Metadata and
        unrelated functions are ignored; no fabricated registration response.
        """
        msg = MtpPacket.parse(packet)
        if msg.type != 2:
            return []
        with self._lock:
            key = (msg.fblock, msg.instance, msg.function)
            # Original RegisterMessageList requests carry mode1, subscriber
            # device ID, then BE16 property IDs. Publish the current hardware
            # state when the native display subscriber actually registers;
            # an earlier unsolicited STATUS can precede its initialization.
            if (key == (0xd1, 2, 1) and msg.operation == 0
                    and len(msg.payload) >= 5 and len(msg.payload) % 2 == 1
                    and msg.payload[0] == 1
                    and int.from_bytes(msg.payload[1:3], 'big') == self.target):
                replies = []
                for offset in range(3, len(msg.payload), 2):
                    fid = int.from_bytes(msg.payload[offset:offset+2], 'big')
                    if fid == 0x430:
                        replies += self.power_status(self.power_raw)
                    elif fid == 0x432:
                        replies += self.monitor_status(self.monitor_enabled)
                return replies
            if key == (0xe5, 1, 0xc30) and msg.operation in (0, 2):
                cfg = RotaryConfiguration.parse(msg.payload)
                changed = cfg != self.configuration
                if changed:
                    self.configuration, self.position = cfg, cfg.start
                    self.pressed.clear()
                self.last_event = {'kind': 'native_rotary_configuration_received',
                                   'handle': cfg.handle, 'mode': cfg.mode, 'count': cfg.count,
                                   'start': cfg.start, 'repeated': not changed}
                return [self._status(0xe5, 1, 0xc30, bytes((1, 29, cfg.handle, 0)))]
            if msg.operation == 1:
                if key == (0xd1, 2, 0x430):
                    return self.power_status(self.power_raw)
                if key == (0xd1, 2, 0x432):
                    return self.monitor_status(self.monitor_enabled)
                if key == (0xe5, 0x0f, 0xc06):
                    return [self.readiness_frame()]
                if key == (0xe5, 1, 0xc10) and self.configuration is not None:
                    return [self._rotary_status(self.position)]
            return []

    def rotate(self, direction):
        """One detent; positive direction increases the native absolute counter."""
        if direction not in (-1, 1):
            raise ValueError('Direction must be -1 or +1')
        with self._lock:
            cfg = self._configured()
            maximum = cfg.count - 1 if cfg.count else 0xffff
            new_position = min(maximum, max(0, self.position + direction))
            if new_position == self.position:
                return []
            self.position = new_position
            return [self._rotary_status(new_position)]

    def _button(self, name):
        if name == 'menu':
            if self.menu_button is None:
                raise ValueError('MENU label not verified; use central_key_1 or an explicit menu_button=(0,1)')
            return self.menu_button
        try:
            return self.BUTTONS[name]
        except KeyError:
            raise ValueError(f'Unsupported native button {name!r}') from None

    def press(self, name):
        with self._lock:
            cfg = self._configured()
            cluster, sensor = self._button(name)
            if name in self.pressed:
                return []
            self.pressed.add(name)
            return [self._status(0xe5, 1, 0xc20, bytes((1, 29, cfg.handle, 1, 0, cluster, sensor)))]

    def release(self, name):
        with self._lock:
            cfg = self._configured()
            cluster, sensor = self._button(name)
            if name not in self.pressed:
                return []
            self.pressed.remove(name)
            return [self._status(0xe5, 1, 0xc20, bytes((1, 29, cfg.handle, 0, 0, cluster, sensor)))]

    def click(self, name):
        """Return press then release; caller controls their delivery interval."""
        with self._lock:
            return self.press(name) + self.release(name)
