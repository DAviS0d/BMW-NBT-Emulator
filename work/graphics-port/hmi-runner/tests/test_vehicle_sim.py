import math
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vehicle_sim import VehicleSimulator


class VehicleSimulatorTests(unittest.TestCase):
    def setUp(self):
        self.sim = VehicleSimulator()
        self.addCleanup(self.sim.close)

    def test_manual_values_drive_sport_outputs_and_snapshot_is_detached(self):
        state = self.sim.update({'ignition': True, 'rpm': 3500, 'throttle_pct': 100,
                                 'doors': {'front_left': True}})
        self.assertEqual(state['torque_nm'], 350)
        self.assertAlmostEqual(state['power_kw'], 350 * 3500 * 2 * math.pi / 60000, places=3)
        state['doors']['front_left'] = False
        self.assertTrue(self.sim.snapshot()['doors']['front_left'])
        self.assertFalse(state['native_injection'])

    def test_invalid_patch_is_atomic_and_rejects_nonfinite_and_booleans(self):
        before = self.sim.snapshot()
        for patch in ({'fuel_pct': 90, 'rpm': float('nan')}, {'speed_kph': True},
                      {'oil_c': float('inf')}, {'torque_nm': 999},
                      {'doors': {'front_left': 1}}, {'ignition': 1}, {'gear': []},
                      {'speed_kph': 50}, {'rpm': 5000}):
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):
                    self.sim.update(patch)
                self.assertEqual(before, self.sim.snapshot())

    def test_ignition_off_removes_power_and_brake_lamp_tracks_braking(self):
        self.sim.update({'ignition': True, 'rpm': 4000, 'throttle_pct': 80, 'brake_pct': 50})
        self.assertTrue(self.sim.snapshot()['lights']['brake'])
        state = self.sim.update({'ignition': False, 'brake_pct': 0})
        self.assertEqual((state['rpm'], state['torque_nm'], state['power_kw']), (0, 0, 0))
        self.assertFalse(state['lights']['brake'])

    def test_drive_accelerates_shifts_consumes_fuel_and_brakes_to_stop(self):
        # Test the deterministic dynamics directly, without scheduler timing.
        with self.sim._lock:
            self.sim._state.update(ignition=True, gear='D')
            self.sim._advance(24)
            fast = self.sim.snapshot()
            self.assertGreater(fast['speed_kph'], 60)
            self.assertGreater(int(fast['gear']), 1)
            self.assertGreater(fast['odometer_km'], 0)
            self.assertLess(fast['fuel_pct'], 75)
            self.assertGreater(fast['coolant_c'], 22)
            self.sim._advance(35)
            stopped = self.sim.snapshot()
            self.assertEqual(stopped['speed_kph'], 0)
            self.assertEqual(stopped['power_kw'], 0)

    def test_demo_and_manual_takeover_and_close(self):
        self.assertTrue(self.sim.start_demo()['demo_running'])
        self.sim.update({'throttle_pct': 40})
        self.assertFalse(self.sim.snapshot()['demo_running'])
        thread = self.sim._thread
        self.sim.close()
        self.assertFalse(thread.is_alive())
        with self.assertRaises(RuntimeError):
            self.sim.start_demo()

    def test_concurrent_updates_do_not_break_derived_power(self):
        self.sim.update({'ignition': True, 'rpm': 3500})
        errors = []
        def worker(throttle):
            for _ in range(100):
                s = self.sim.update({'throttle_pct': throttle})
                expected = s['torque_nm'] * s['rpm'] * 2 * math.pi / 60000
                if abs(s['power_kw'] - expected) > .002:
                    errors.append(s)
        threads = [threading.Thread(target=worker, args=(n,)) for n in (10, 40, 90)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])


if __name__ == '__main__':
    unittest.main()
