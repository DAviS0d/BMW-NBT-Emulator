import ctypes
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'native-controls'))
from native_mailbox import NativeMailbox


class MailboxTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        folder=Path(self.directory.name)
        (folder/'dma-config.txt').write_text('123 100000000 20000000 abc\n')
        (folder/'serial_com1.log').write_text('NBT_NATIVE_MAILBOX physical=0x10000 bytes=4096 version=1\n')
        self.kernel=Mock()
        self.kernel.OpenProcess.return_value=789
        def times(handle,creation,*others):
            ctypes.cast(creation,ctypes.POINTER(ctypes.c_uint64))[0]=0xabc
            return 1
        self.kernel.GetProcessTimes.side_effect=times
        self.header=[0x5854424e,1,0,0,0,1,13,2,1]
        def read(handle,address,buffer,size,actual):
            payload=struct.pack('<9I',*self.header)
            ctypes.memmove(buffer,payload,len(payload))
            ctypes.cast(actual,ctypes.POINTER(ctypes.c_size_t))[0]=len(payload)
            return 1
        self.kernel.ReadProcessMemory.side_effect=read
        self.writes=[]
        def write(handle,address,buffer,size,actual):
            self.writes.append((address,ctypes.string_at(buffer,size)))
            ctypes.cast(actual,ctypes.POINTER(ctypes.c_size_t))[0]=size
            return 1
        self.kernel.WriteProcessMemory.side_effect=write
        with patch('native_mailbox.ctypes.WinDLL',return_value=self.kernel):
            self.mailbox=NativeMailbox(folder)
        self.addCleanup(self.mailbox.close)

    def test_exchange_requires_identity_and_lifetime_then_writes_only_telemetry(self):
        selected,ack=self.mailbox.exchange(50,75)
        self.assertEqual((selected,ack),(13,2))
        self.assertEqual(self.writes,[(0x10001000c,struct.pack('<II',50,75)),(0x100010008,struct.pack('<I',1))])
        selected,ack=self.mailbox.exchange(20,30)
        self.assertEqual((selected,ack),(None,None))

    def test_bad_magic_and_reused_pid_never_write_guest_memory(self):
        self.header[0]=0
        with self.assertRaises(OSError):self.mailbox.exchange(10,20)
        self.assertFalse(self.writes)
        self.header[0]=0x5854424e
        self.kernel.GetProcessTimes.return_value=0
        self.kernel.GetProcessTimes.side_effect=lambda *args:0
        with self.assertRaises(OSError):self.mailbox.exchange(10,20)
        self.assertFalse(self.writes)

    def test_bounds_reject_invalid_percent_and_write_ranges(self):
        with self.assertRaises(ValueError):self.mailbox.exchange(101,0)
        for offset,payload in [(0,b'1234'),(8,b'12345678'),(20,b'1234')]:
            with self.assertRaises(ValueError):self.mailbox._write(offset,payload)


if __name__=='__main__':unittest.main()
