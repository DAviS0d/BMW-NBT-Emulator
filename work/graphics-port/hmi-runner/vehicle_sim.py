"""Thread-safe host vehicle simulation; no CAN/MOST or original-HMI injection.

All reported values are simulated, including the engine torque/power estimates.
The model supplies the local web interface and can later feed a separately
verified native transport. It does not claim to emulate a specific BMW engine.
"""
import math
import threading
import time
from collections.abc import Mapping


class VehicleSimulator:
    NUMERIC = {
        'speed_kph': (0, 300), 'rpm': (0, 8000),
        'throttle_pct': (0, 100), 'brake_pct': (0, 100),
        'coolant_c': (-40, 130), 'oil_c': (-40, 160),
        'fuel_pct': (0, 100), 'odometer_km': (0, 2_000_000),
    }
    DOORS = ('front_left', 'front_right', 'rear_left', 'rear_right', 'hood', 'trunk')
    LIGHTS = ('headlights', 'brake', 'left_indicator', 'right_indicator')
    GEARS = ('P', 'R', 'N', 'D', '1', '2', '3', '4', '5', '6', '7', '8')
    GEAR_RATIOS = (4.7, 3.1, 2.1, 1.67, 1.29, 1.0, .84, .67)

    def __init__(self):
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._closed = False
        self._demo = False
        self._elapsed = 0.0
        self._state = {
            'speed_kph': 0.0, 'rpm': 0.0, 'throttle_pct': 0.0,
            'brake_pct': 0.0, 'ignition': False, 'gear': 'P',
            'torque_nm': 0.0, 'power_kw': 0.0,
            'coolant_c': 22.0, 'oil_c': 22.0, 'fuel_pct': 75.0,
            'odometer_km': 0.0,
            'doors': dict.fromkeys(self.DOORS, False),
            'lights': dict.fromkeys(self.LIGHTS, False),
        }

    def snapshot(self):
        with self._lock:
            state = {k: round(v, 3) if isinstance(v, float) else v
                     for k, v in self._state.items()}
            state['doors'] = dict(self._state['doors'])
            state['lights'] = dict(self._state['lights'])
            state.update(demo_running=self._demo, native_injection=False,
                         source='host_vehicle_simulator',
                         demo_elapsed_seconds=round(self._elapsed, 3),
                         power_hp=round(self._state['power_kw'] * 1.34102209, 1))
            return state

    @classmethod
    def _validate(cls, patch):
        if not isinstance(patch, Mapping):
            raise ValueError('Vehicle update must be an object')
        cleaned = {}
        for key, value in patch.items():
            if key in cls.NUMERIC:
                low, high = cls.NUMERIC[key]
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or not low <= value <= high or not math.isfinite(value)):
                    raise ValueError(f'{key} must be a finite number in {low}..{high}')
                cleaned[key] = float(value)
            elif key == 'ignition':
                if type(value) is not bool:
                    raise ValueError('ignition must be true or false')
                cleaned[key] = value
            elif key == 'gear':
                if not isinstance(value, str) or value not in cls.GEARS:
                    raise ValueError('gear must be P, R, N, D, or 1..8')
                cleaned[key] = value
            elif key in ('doors', 'lights'):
                allowed = cls.DOORS if key == 'doors' else cls.LIGHTS
                if (not isinstance(value, Mapping) or any(k not in allowed for k in value)
                        or any(type(v) is not bool for v in value.values())):
                    raise ValueError(f'{key} must contain named boolean states')
                cleaned[key] = dict(value)
            else:
                raise ValueError(f'Unknown or read-only vehicle field: {key}')
        return cleaned

    def update(self, patch):
        """Validate and apply a manual update atomically; leave demo mode.

        Torque and power are derived from RPM and throttle. Doors/lights accept
        partial objects. Invalid updates change neither state nor demo mode.
        """
        cleaned = self._validate(patch)
        with self._lock:
            if self._closed:
                raise RuntimeError('Vehicle simulator is closed')
            candidate = dict(self._state)
            for key, value in cleaned.items():
                candidate[key] = ({**candidate[key], **value}
                                  if key in ('doors', 'lights') else value)
            if candidate['gear'] == 'P' and candidate['speed_kph'] > 0:
                raise ValueError('Park requires zero speed; choose a drive gear first')
            if not candidate['ignition'] and cleaned.get('rpm', 0) > 0:
                raise ValueError('RPM requires ignition')
            self._demo = False
            self._state = candidate
            if self._state['ignition'] and self._state['rpm'] == 0:
                self._state['rpm'] = 750.0
            self._derive()
            return self.snapshot()

    def _derive(self):
        s = self._state
        if not s['ignition'] or s['fuel_pct'] <= 0:
            s['rpm'] = s['throttle_pct'] = 0.0
            s['torque_nm'] = s['power_kw'] = 0.0
        else:
            # A smooth illustrative torque curve, not vehicle calibration data.
            maximum = max(0.0, 350 * (1 - .35 * ((s['rpm'] - 3500) / 3500) ** 2))
            s['torque_nm'] = maximum * s['throttle_pct'] / 100
            s['power_kw'] = s['torque_nm'] * s['rpm'] * (2 * math.pi / 60) / 1000
        s['lights']['brake'] = s['brake_pct'] > 1

    def start_demo(self):
        """Start a repeatable automatic drive, with acceleration and braking."""
        with self._lock:
            if self._closed:
                raise RuntimeError('Vehicle simulator is closed')
            if self._demo:
                return self.snapshot()
            if self._state['fuel_pct'] <= 0:
                raise ValueError('Add fuel before starting the drive demo')
            self._demo = True
            self._elapsed = 0.0
            self._state.update(ignition=True, gear='D', rpm=750.0,
                               throttle_pct=0.0, brake_pct=0.0)
            self._derive()
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name='vehicle-simulator', daemon=True)
                self._thread.start()
            return self.snapshot()

    def stop_demo(self):
        """Freeze speed/RPM at their current values and release the pedals."""
        with self._lock:
            self._demo = False
            self._state.update(throttle_pct=0.0, brake_pct=0.0)
            self._derive()
            return self.snapshot()

    def _run(self):
        previous = time.monotonic()
        while not self._stop.wait(.05):
            now = time.monotonic()
            with self._lock:
                if self._demo:
                    # Do not jump the car forward after host suspension.
                    self._advance(min(now - previous, .25))
            previous = now

    def _advance(self, seconds):
        """Advance under the lock; substeps make deterministic model tests possible."""
        while seconds > 1e-9:
            dt = min(seconds, .05)
            seconds -= dt
            self._elapsed += dt
            phase = self._elapsed % 60
            s = self._state
            # 0..3 idle; 3..24 accelerate; 24..40 cruise; 40..56 brake; 56..60 idle.
            if phase < 3 or phase >= 56:
                throttle, brake = 0.0, 50.0 if s['speed_kph'] > 0 else 0.0
            elif phase < 24:
                throttle, brake = 58.0, 0.0
            elif phase < 40:
                throttle = max(0.0, min(40.0, 14 + (90 - s['speed_kph']) * 2))
                brake = 0.0
            else:
                throttle, brake = 0.0, 28.0
            s.update(throttle_pct=throttle, brake_pct=brake)
            number = min(8, 1 + sum(s['speed_kph'] >= n for n in (22, 42, 65, 90, 120, 150, 180)))
            s['gear'] = str(number)
            ratio = self.GEAR_RATIOS[number - 1] * 3.15
            speed_ms = s['speed_kph'] / 3.6
            s['rpm'] = min(7500.0, max(750.0, speed_ms / (2 * math.pi * .33) * 60 * ratio))
            self._derive()
            force = s['torque_nm'] * ratio * .88 / .33
            resistance = 190 + .40 * speed_ms * speed_ms
            acceleration = (force - resistance) / 1600 - brake / 100 * 8
            new_speed = max(0.0, min(300.0, (speed_ms + acceleration * dt) * 3.6))
            s['odometer_km'] += (s['speed_kph'] + new_speed) / 2 * dt / 3600
            s['speed_kph'] = new_speed
            fuel_litres = (.7 + s['power_kw'] * .27) * dt / 3600
            s['fuel_pct'] = max(0.0, s['fuel_pct'] - fuel_litres / 60 * 100)
            s['coolant_c'] += (92 - s['coolant_c']) * dt / 180
            s['oil_c'] += (102 - s['oil_c']) * dt / 300
            s['lights']['left_indicator'] = 24 <= phase < 28
            if s['fuel_pct'] <= 0:
                self._demo = False
                self._derive()
                break

    def close(self):
        with self._lock:
            self._closed = True
            self._demo = False
            self._stop.set()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)


# Short alias for callers that use a vehicle-state service name.
VehicleSim = VehicleSimulator
