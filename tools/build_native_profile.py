"""Build a separate native profile while retaining the shipped GLES bridge."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
from inspect_nbt_ifs import find_imagefs
from patch_external_devices import patch_resource
from repack_nbt_ifs import repack

ROOT=Path(__file__).resolve().parents[1]
BRIDGE=ROOT/'work/bridge-v2'


def patch_startup(data):
    result=bytearray()
    offset=0
    replaced=0
    while offset+4<=len(data):
        size=struct.unpack_from('<H',data,offset)[0]
        if not size:
            result.extend(data[offset:])
            break
        if size<4 or offset+size>len(data):
            raise ValueError('Invalid QNX startup-script record')
        record=data[offset:offset+size]
        needle=b':/boot/lib/libnbtgl.so:'
        if needle in record:
            if record[2]!=0 or record.count(needle)!=1:
                raise ValueError('Unexpected native preload record')
            record=record.replace(needle,b':/boot/lib/libnbtnative.so:/boot/lib/libnbtgl.so:')
            record=bytearray(record)
            record.extend(b'\0'*(-len(record)%4))
            struct.pack_into('<H',record,0,len(record))
            replaced+=1
        result.extend(record)
        offset+=size
    if replaced!=1:
        raise ValueError('Expected exactly one original HMI preload command')
    return bytes(result)


def main():
    source=BRIDGE/'ifs/walthread_keyboard_dma_v2_prio.ifs'
    destination=BRIDGE/'ifs/walthread_keyboard_dma_v2_native.ifs'
    work=ROOT/'outputs/native-integration'/('build-'+str(time.time_ns()))
    work.mkdir(parents=True)
    spec=importlib.util.spec_from_file_location('bridge_build',BRIDGE/'build.py')
    build=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    library=work/'libnbtnative.so'
    flags=[x.replace('soname,libnbtgl.so','soname,libnbtnative.so') for x in build.GUEST_FLAGS]
    subprocess.run([build.ZIG,'cc',*flags,'-DNBT_EXPERIMENTAL_NATIVE=1','-DNBT_STANDALONE_NATIVE=1','-o',str(library),
                    *[str(BRIDGE/'guest'/name) for name in ('rt.c','native_patch.c','native_sports.c','native_devices.c','native_menu.c','native_addon.c')]],check=True)
    data=source.read_bytes()
    inventory=find_imagefs(data)
    def get(path):
        entry=next(x for x in inventory['entries'] if x['path']==path)
        return data[entry['absolute_offset']:entry['absolute_offset']+entry['size']]
    if hashlib.sha256(get('boot/bin/HmiMain3D')).hexdigest()!='554b67d4d6317cfb1715d544874fae8ddd2c975be503c9e2514e2dc2f3a0d693':
        raise ValueError('Native adapter does not support this HmiMain3D version')
    resource=work/'hmimultimedia.pba'
    resource.write_bytes(patch_resource(get('opt/hmi/data/ro/app/hmimultimedia/hmimultimedia.pba'))[0])
    script=work/'startupscript.bin'
    script.write_bytes(patch_startup(get('proc/boot/.startupscript')))
    output=work/'native.ifs'
    manifest=repack(source,output,{'proc/boot/.startupscript':script,
                   'opt/hmi/data/ro/app/hmimultimedia/hmimultimedia.pba':resource},
                   {'boot/lib/libnbtnative.so':library})
    # Verify the complete original GLES bridge was retained.
    native=output.read_bytes()
    new_inventory=find_imagefs(native)
    entry=next(x for x in new_inventory['entries'] if x['path']=='boot/lib/libnbtgl.so')
    assert native[entry['absolute_offset']:entry['absolute_offset']+entry['size']]==get('boot/lib/libnbtgl.so')
    manifest['original_gles_bridge_preserved']=True
    manifest['output']=str(destination)
    output.replace(destination)
    destination.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Built native profile:',destination)
    print('SHA-256:',hashlib.sha256(native).hexdigest())
    print('Original GLES bridge preserved; patched menu and standalone native adapter included.')


if __name__=='__main__': main()
