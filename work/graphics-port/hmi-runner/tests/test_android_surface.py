import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from android_surface import AndroidSurface


class AndroidTests(unittest.TestCase):
    def test_no_phone_does_not_start_a_receiver(self):
        result=Mock(stdout='List of devices attached\n\n',returncode=0)
        with patch('android_surface.subprocess.run',return_value=result), patch('android_surface.subprocess.Popen') as launch:
            surface=AndroidSurface()
            with self.assertRaises(RuntimeError): surface.start()
            launch.assert_not_called()

    def test_original_dhu_commands_are_used(self):
        surface=AndroidSurface()
        surface.process=Mock()
        surface.process.poll.return_value=None
        surface.process.stdin=io.StringIO()
        for name in ('up','down','select','back'): surface.action(name)
        self.assertEqual(surface.process.stdin.getvalue(),'dpad rotate left\ndpad rotate right\ndpad click\ndpad back\n')


if __name__ == '__main__': unittest.main()
