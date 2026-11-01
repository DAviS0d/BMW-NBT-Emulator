"""Inspect the connected iPhone through its existing WinUSB driver; no driver replacement.

--enable-carplay issues the iPhone's CarPlay USB mode request, then closes the
handle so Windows can enumerate the new mode. No pairing material is read.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import uuid
import pathlib
import sys


class GUID(C.Structure):
    _fields_ = [('bytes', C.c_ubyte * 16)]


class Interface(C.Structure):
    _fields_ = [('size', W.DWORD), ('guid', GUID), ('flags', W.DWORD), ('reserved', C.c_void_p)]


class Setup(C.Structure):
    _pack_ = 1
    _fields_ = [('type', C.c_ubyte), ('request', C.c_ubyte), ('value', C.c_ushort),
                ('index', C.c_ushort), ('length', C.c_ushort)]


def open_iphone():
    setup = C.WinDLL('setupapi', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    usb = C.WinDLL('winusb', use_last_error=True)
    setup.SetupDiGetClassDevsW.argtypes = [C.POINTER(GUID), W.LPCWSTR, W.HWND, W.DWORD]
    setup.SetupDiGetClassDevsW.restype = W.HANDLE
    setup.SetupDiEnumDeviceInterfaces.argtypes = [W.HANDLE, C.c_void_p, C.POINTER(GUID), W.DWORD, C.POINTER(Interface)]
    setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [W.HANDLE, C.POINTER(Interface), C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    setup.SetupDiDestroyDeviceInfoList.argtypes = [W.HANDLE]
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE]
    usb.WinUsb_Initialize.argtypes = [W.HANDLE, C.POINTER(W.HANDLE)]
    usb.WinUsb_Free.argtypes = [W.HANDLE]
    usb.WinUsb_ControlTransfer.argtypes = [W.HANDLE, Setup, C.c_void_p, W.ULONG, C.POINTER(W.ULONG), C.c_void_p]
    guid = GUID((C.c_ubyte * 16).from_buffer_copy(uuid.UUID('664be590-54bd-4964-8a8c-6cd1314f6dc2').bytes_le))
    devices = setup.SetupDiGetClassDevsW(C.byref(guid), None, None, 0x12)
    invalid = C.c_void_p(-1).value
    if devices == invalid:
        raise C.WinError(C.get_last_error())
    errors = []
    try:
        for index in range(128):
            interface = Interface(size=C.sizeof(Interface))
            if not setup.SetupDiEnumDeviceInterfaces(devices, None, C.byref(guid), index, C.byref(interface)):
                break
            required = W.DWORD()
            setup.SetupDiGetDeviceInterfaceDetailW(devices, C.byref(interface), None, 0, C.byref(required), None)
            detail = C.create_string_buffer(required.value)
            C.cast(detail, C.POINTER(W.DWORD))[0] = 8 if C.sizeof(C.c_void_p) == 8 else 6
            if not setup.SetupDiGetDeviceInterfaceDetailW(devices, C.byref(interface), detail, required.value, None, None):
                continue
            path = C.wstring_at(C.addressof(detail) + 4)
            if 'vid_05ac' not in path.lower():
                continue
            handle = kernel.CreateFileW(path, 0xC0000000, 3, None, 3, 0x40000000, None)
            if handle == invalid:
                errors.append('open error %d' % C.get_last_error())
                continue
            pipe = W.HANDLE()
            if not usb.WinUsb_Initialize(handle, C.byref(pipe)):
                errors.append('WinUSB initialization error %d' % C.get_last_error())
                kernel.CloseHandle(handle)
                continue
            return kernel, usb, handle, pipe
    finally:
        setup.SetupDiDestroyDeviceInfoList(devices)
    raise RuntimeError('No accessible iPhone WinUSB interface. Unlock/trust the phone. ' + '; '.join(errors))


def control(usb, pipe, kind, request, value=0, index=0, length=256):
    buffer = (C.c_ubyte * max(1, length))()
    count = W.ULONG()
    if not usb.WinUsb_ControlTransfer(pipe, Setup(kind, request, value, index, length), buffer, length, C.byref(count), None):
        raise C.WinError(C.get_last_error())
    return bytes(buffer[:count.value])


def describe(raw):
    interfaces = []
    cursor = 0
    while cursor + 2 <= len(raw):
        size, kind = raw[cursor:cursor + 2]
        if size < 2 or cursor + size > len(raw):
            raise ValueError('Malformed USB descriptor')
        if kind == 4 and size >= 9:
            interfaces.append({'id': raw[cursor + 2], 'alt': raw[cursor + 3],
                               'class': '%02x.%02x.%02x' % tuple(raw[cursor + 5:cursor + 8])})
        cursor += size
    return {'configuration': raw[5], 'interfaces': interfaces}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enable-carplay', action='store_true')
    parser.add_argument('--usbdk', action='store_true', help='Use the already-installed UsbDk capture driver')
    args = parser.parse_args()
    if args.usbdk:
        return probe_usbdk(args.enable_carplay)
    kernel, usb, handle, pipe = open_iphone()
    try:
        descriptor = control(usb, pipe, 0x80, 6, 0x0100, length=18)
        configs = []
        for index in range(descriptor[17]):
            raw = control(usb, pipe, 0x80, 6, 0x0200 | index, length=4096)
            configs.append(describe(raw))
        result = {'vendor': '%04x' % int.from_bytes(descriptor[8:10], 'little'),
                  'product': '%04x' % int.from_bytes(descriptor[10:12], 'little'), 'configurations': configs}
        try:
            result['activeConfiguration'] = list(control(usb, pipe, 0x80, 8, length=1))
            result['usbMode'] = list(control(usb, pipe, 0xc0, 0x45, length=4))
        except OSError as error:
            result['modeReadError'] = str(error)
        print(json.dumps(result, indent=2), flush=True)
        if args.enable_carplay:
            response = control(usb, pipe, 0xc0, 0x52, index=4, length=1)
            print('CarPlay mode request accepted: ' + response.hex(), flush=True)
    finally:
        usb.WinUsb_Free(pipe)
        kernel.CloseHandle(handle)


def probe_usbdk(enable):
    # work/carplay/python: pyusb and libusb-1.0.dll bundled with the emulator.
    python = pathlib.Path(__file__).resolve().parents[1] / 'python'
    sys.path.insert(0, str(python))
    import usb.core
    import usb.util
    import usb.backend.libusb1
    backend = usb.backend.libusb1.get_backend(find_library=lambda _: str(python / 'libusb-1.0.dll'))
    if backend is None:
        raise RuntimeError('64-bit Python and the libusb DLL are required')
    backend.lib.libusb_set_option.argtypes = [C.c_void_p, C.c_int]
    result = backend.lib.libusb_set_option(backend.ctx, 1)  # LIBUSB_OPTION_USE_USBDK
    if result != 0:
        raise RuntimeError('UsbDk backend unavailable: %d' % result)
    phones = [device for device in usb.core.find(find_all=True, idVendor=0x05ac, backend=backend)
              if 0x1290 <= device.idProduct <= 0x12af]
    if len(phones) != 1:
        raise RuntimeError('Connect exactly one iPhone in its normal USB mode')
    phone = phones[0]
    try:
        configs = []
        for config in phone:
            configs.append({'configuration': config.bConfigurationValue, 'interfaces': [
                {'id': i.bInterfaceNumber, 'alt': i.bAlternateSetting,
                 'class': '%02x.%02x.%02x' % (i.bInterfaceClass, i.bInterfaceSubClass, i.bInterfaceProtocol),
                 'endpoints': ['%02x' % e.bEndpointAddress for e in i]} for i in config]})
        print(json.dumps({'vendor': '%04x' % phone.idVendor, 'product': '%04x' % phone.idProduct, 'configurations': configs}, indent=2), flush=True)
        print('activeConfiguration:', list(phone.ctrl_transfer(0x80, 8, 0, 0, 1, timeout=3000)), flush=True)
        try:
            print('usbMode:', list(phone.ctrl_transfer(0xc0, 0x45, 0, 0, 4, timeout=3000)), flush=True)
        except usb.core.USBError as error:
            print('USB mode diagnostic unavailable:', error, flush=True)
        if enable:
            response = phone.ctrl_transfer(0xc0, 0x52, 0, 4, 1, timeout=3000)
            print('CarPlay mode request accepted:', bytes(response).hex(), flush=True)
    finally:
        usb.util.dispose_resources(phone)


if __name__ == '__main__':
    main()
