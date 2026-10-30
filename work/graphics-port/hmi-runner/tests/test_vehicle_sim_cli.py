import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = Path(__file__).resolve().parents[1] / 'vehicle_sim_cli.py'


class VehicleSimulatorCLITests(unittest.TestCase):
    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, str(CLI), *args], input=input,
                              capture_output=True, text=True, timeout=10)

    def test_manual_patch_emits_one_derived_json_snapshot(self):
        result = self.run_cli('--state-json', json.dumps({
            'ignition': True, 'rpm': 3500, 'throttle_pct': 70}))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        state = json.loads(lines[0])
        self.assertEqual(state['torque_nm'], 245)
        self.assertGreater(state['power_kw'], 0)
        self.assertFalse(state['native_injection'])

    def test_demo_stream_and_atomic_output_contain_same_final_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'nested' / 'state.json'
            result = self.run_cli('--demo', '--seconds', '.2', '--hz', '20',
                                  '--output', str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            samples = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertGreaterEqual(len(samples), 3)
            self.assertTrue(all(s['demo_running'] for s in samples))
            self.assertGreater(samples[-1]['demo_elapsed_seconds'], 0)
            self.assertEqual(json.loads(path.read_text()), samples[-1])
            self.assertEqual(list(path.parent.glob('*.tmp')), [])

    def test_interactive_patch_and_eof_exit(self):
        result = self.run_cli('--interactive', input='{"ignition":true,"rpm":2000}\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout.splitlines()[-1])
        self.assertTrue(state['ignition'])
        self.assertEqual(state['rpm'], 2000)

    def test_initial_patch_can_be_loaded_from_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            patch = Path(temporary) / 'manual.json'
            patch.write_text('{"ignition": true, "gear": "D", "speed_kph": 40}')
            result = self.run_cli('--state-json', '@' + str(patch))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['speed_kph'], 40)

    def test_invalid_initial_state_and_rate_fail_without_output(self):
        for args in (('--state-json', '{"rpm":70000}'), ('--hz', 'nan'),
                     ('--seconds', '-1')):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
