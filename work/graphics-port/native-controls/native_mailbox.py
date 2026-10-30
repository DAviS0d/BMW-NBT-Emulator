"""Owned-QEMU access limited to the guest native adapter's declared mailbox."""
import ctypes
from pathlib import Path
import re
import struct


class NativeMailbox:
    def __init__(self, folder):
        self.folder=Path(folder)
        self.handle=None
        self.address=None
        self.sequence=0
        self.event_sequence=0
        self.applied_sequence=0
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
        self.kernel.OpenProcess.restype=ctypes.c_void_p
        self.kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        self.kernel.GetProcessTimes.argtypes=[ctypes.c_void_p,*([ctypes.POINTER(ctypes.c_uint64)]*4)]
        self.kernel.ReadProcessMemory.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        self.kernel.WriteProcessMemory.argtypes=self.kernel.ReadProcessMemory.argtypes

    def _read(self):
        buffer=ctypes.create_string_buffer(36)
        actual=ctypes.c_size_t()
        if not self.kernel.ReadProcessMemory(self.handle,self.address,buffer,36,ctypes.byref(actual)) or actual.value!=36:
            raise OSError(ctypes.get_last_error(),'Cannot read the native mailbox')
        values=struct.unpack('<9I',buffer.raw)
        if values[:2]!=(0x5854424e,1):
            raise OSError('Native mailbox identity mismatch')
        return values

    def _attach(self):
        if struct.calcsize('P')!=8:
            raise OSError('Native adapter requires 64-bit Python')
        try:
            fields=(self.folder/'dma-config.txt').read_text().split()
            log=(self.folder/'serial_com1.log').read_text(errors='replace')
        except OSError:
            return False
        match=re.search(r'NBT_NATIVE_MAILBOX physical=0x([0-9a-fA-F]+) bytes=4096 version=1',log)
        if not match or len(fields)!=4:
            return False
        pid=int(fields[0]); base,size,created=(int(value,16) for value in fields[1:])
        physical=int(match[1],16)
        if size!=0x20000000 or not 0<=physical<=size-4096:
            raise OSError('Native mailbox is outside the owned guest RAM')
        handle=self.kernel.OpenProcess(0x1038,False,pid)
        if not handle:
            raise OSError(ctypes.get_last_error(),'Cannot open owned QEMU process')
        timestamps=[ctypes.c_uint64() for _ in range(4)]
        if (not self.kernel.GetProcessTimes(handle,*[ctypes.byref(v) for v in timestamps])
                or timestamps[0].value!=created):
            self.kernel.CloseHandle(handle)
            raise OSError('QEMU process lifetime does not match this run')
        self.handle,self.address=handle,base+physical
        try:
            self._read()
        except OSError:
            self.close()
            raise
        return True

    def _write(self, offset, payload):
        if (offset,len(payload)) not in {(8,4),(12,8)}:
            raise ValueError('Write exceeds native telemetry fields')
        buffer=ctypes.create_string_buffer(payload)
        actual=ctypes.c_size_t()
        if not self.kernel.WriteProcessMemory(self.handle,self.address+offset,buffer,len(payload),ctypes.byref(actual)) or actual.value!=len(payload):
            raise OSError(ctypes.get_last_error(),'Cannot publish native telemetry')

    def exchange(self,power,torque):
        if not 0<=power<=100 or not 0<=torque<=100:
            raise ValueError('Native gauge percentages must be 0..100')
        if not self.handle and not self._attach():
            return None,None
        values=self._read()
        selected=None
        if values[5]!=self.event_sequence:
            self.event_sequence=values[5]
            selected=values[6]
        applied=None
        if values[7]!=self.applied_sequence:
            self.applied_sequence=values[7]
            applied=values[7]
        self.sequence=(self.sequence+1)&0xffffffff or 1
        self._write(12,struct.pack('<II',power,torque))
        self._write(8,struct.pack('<I',self.sequence))
        return selected,applied

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
        self.handle=self.address=None
