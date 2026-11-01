"""Wired iAP2 pipe through Apple's installed USB multiplexing service.

Only this machine's existing pairing record for the physically attached phone is
used. With --carkit, stdout contains protocol bytes only; diagnostics go to stderr.
"""
import argparse
import contextlib
import json
import os
import pathlib
import plistlib
import socket
import ssl
import struct
import sys
import tempfile
import threading


def read_exact(stream, size):
    result = bytearray()
    while len(result) < size:
        chunk = stream.recv(size - len(result))
        if not chunk:
            raise EOFError('iPhone closed the USB service')
        result.extend(chunk)
    return bytes(result)


def mux_request(request):
    stream = socket.create_connection(('127.0.0.1', 27015), timeout=5)
    try:
        payload = plistlib.dumps({'ClientVersionString': 'mib2emu', 'ProgName': 'mib2emu',
                                 'kLibUSBMuxVersion': 3, **request})
        stream.sendall(struct.pack('<IIII', len(payload) + 16, 1, 8, 1) + payload)
        header = read_exact(stream, 16)
        length, version, kind, _ = struct.unpack('<IIII', header)
        if version != 1 or kind != 8 or not 16 <= length <= 4 * 1024 * 1024:
            raise ValueError('Invalid Apple USB multiplexing reply')
        return stream, plistlib.loads(read_exact(stream, length - 16))
    except BaseException:
        stream.close()
        raise


def phone_device():
    stream, reply = mux_request({'MessageType': 'ListDevices'})
    stream.close()
    devices = [d for d in reply.get('DeviceList', []) if d.get('Properties', {}).get('ConnectionType', 'USB') == 'USB']
    if len(devices) != 1:
        raise RuntimeError('Connect exactly one unlocked/trusted iPhone by USB (found %d)' % len(devices))
    return devices[0]


def connect(device, port):
    stream, reply = mux_request({'MessageType': 'Connect', 'DeviceID': device['DeviceID'],
                                 'PortNumber': socket.htons(port)})
    if reply.get('Number') != 0:
        stream.close()
        raise RuntimeError('Apple USB Connect failed: %s' % reply.get('Number'))
    return stream


def plist_request(stream, request):
    payload = plistlib.dumps({'Label': 'mib2emu', **request})
    stream.sendall(struct.pack('>I', len(payload)) + payload)
    length, = struct.unpack('>I', read_exact(stream, 4))
    if not 0 < length <= 4 * 1024 * 1024:
        raise ValueError('Invalid Lockdown reply length')
    reply = plistlib.loads(read_exact(stream, length))
    if 'Error' in reply:
        raise RuntimeError('Lockdown %s: %s' % (request.get('Request'), reply['Error']))
    return reply


def pair_record(device):
    serial = device['Properties']['SerialNumber']
    path = pathlib.Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData')) / 'Apple/Lockdown' / (serial + '.plist')
    with path.open('rb') as handle:
        record = plistlib.load(handle)
    if not all(key in record for key in ('HostID', 'HostCertificate', 'HostPrivateKey', 'DeviceCertificate')):
        raise RuntimeError('Pairing record incomplete; unlock and trust this computer again')
    if 'SystemBUID' not in record:
        with (path.parent / 'SystemConfiguration.plist').open('rb') as handle:
            record['SystemBUID'] = plistlib.load(handle)['SystemBUID']
    return record


def secure(stream, record):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.set_ciphers('ALL:@SECLEVEL=0')
    # Apple Lockdown uses the certificates from its locally approved pairing.
    # Pin the remote certificate below instead of relying on public web CAs.
    fd, path = tempfile.mkstemp(prefix='mib2emu-usb-', suffix='.pem')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(record['HostCertificate'] + b'\n' + record['HostPrivateKey'])
        context.load_cert_chain(path)
    finally:
        os.unlink(path)
    wrapped = context.wrap_socket(stream, server_hostname=None)
    expected = ssl.PEM_cert_to_DER_cert(record['DeviceCertificate'].decode('ascii'))
    if wrapped.getpeercert(binary_form=True) != expected:
        wrapped.close()
        raise RuntimeError('iPhone TLS certificate differs from the trusted local pairing record')
    return wrapped


@contextlib.contextmanager
def carkit(device):
    record = pair_record(device)
    lockdown = connect(device, 62078)
    service = None
    try:
        response = plist_request(lockdown, {'Request': 'StartSession', 'HostID': record['HostID'], 'SystemBUID': record['SystemBUID']})
        if response.get('EnableSessionSSL'):
            lockdown = secure(lockdown, record)
        response = plist_request(lockdown, {'Request': 'StartService', 'Service': 'com.apple.carkit.service'})
        service = connect(device, response['Port'])
        if response.get('EnableServiceSSL'):
            service = secure(service, record)
        yield service
    finally:
        if service is not None:
            service.close()
        lockdown.close()


def pump(stream):
    stream.settimeout(None)
    def upstream():
        try:
            while True:
                data = sys.stdin.buffer.read1(8192)
                if not data:
                    break
                stream.sendall(data)
        finally:
            with contextlib.suppress(OSError):
                stream.shutdown(socket.SHUT_RDWR)
    threading.Thread(target=upstream, daemon=True).start()
    while True:
        data = stream.recv(8192)
        if not data:
            return
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--carkit', action='store_true')
    parser.add_argument('--check-carkit', action='store_true')
    args = parser.parse_args()
    device = phone_device()
    if args.carkit or args.check_carkit:
        with carkit(device) as stream:
            print('USB carkit service opened', file=sys.stderr, flush=True)
            if args.carkit:
                pump(stream)
        return
    with connect(device, 62078) as stream:
        values = plist_request(stream, {'Request': 'GetValue'}).get('Value', {})
        print(json.dumps({key: values.get(key) for key in ('DeviceName', 'ProductType', 'ProductVersion')}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('usb-carkit: ' + str(error), file=sys.stderr)
        sys.exit(1)
