#!/usr/bin/env python3
"""Prepare the matching source-pinned ARMv7 graphics trial for media services."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SHA256 = '22cfe3933fd03f82d44455ae92ebf72cb6b34ea682699f202945eec0c769fcad'
PREVIOUS_PATCHED_SHA256 = '2d562bf0fbec56c6c741827d1299a5ac603cfc0564aaa7cd8b7940b8026684c4'
PATCHED_SHA256 = 'cc58d7555489fba8caa60889ca1dc69e05192135681e36a53a5b1b7bd14cb7f3'
STUB = 0xabe0


def assemble():
    with tempfile.TemporaryDirectory(prefix='ooscamera-thumb-') as directory:
        obj, binary = Path(directory) / 'patch.o', Path(directory) / 'patch.bin'
        subprocess.run(['llvm-mc', '-triple=thumbv7-linux-android', '-filetype=obj',
                        str(ROOT / 'patches/gralloc32-legacy-camera.s'), '-o', str(obj)], check=True)
        subprocess.run(['llvm-objcopy', '-O', 'binary', '--only-section=.text',
                        str(obj), str(binary)], check=True)
        return binary.read_bytes()


def patch(data):
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unexpected ARMv7 ROM graphics library; refusing an unpinned patch')
    if data[:6] != b'\x7fELF\x01\x01' or struct.unpack_from('<H', data, 18)[0] != 40:
        raise ValueError('Expected little-endian ELF32 ARM')
    phoff = struct.unpack_from('<I', data, 28)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 42)
    if phsize != 32:
        raise ValueError('Unexpected ELF32 program-header size')
    headers = [list(struct.unpack_from('<8I', data, phoff + i * phsize)) for i in range(phnum)]
    candidates = [(i, h) for i, h in enumerate(headers)
                  if h == [1, 0x3ca0, 0x4ca0, 0x4ca0, 0x5f40, 0x5f40, 5, 0x1000]]
    if len(candidates) != 1:
        raise ValueError('Unexpected ARMv7 executable segment')
    index, header = candidates[0]
    old_offset, address, size = header[1], header[2], header[4]
    assembled = assemble()
    code = bytearray(data[old_offset:old_offset + size])
    for entry, original in [(0x7d8c, bytes.fromhex('40f60440'))]:
        offset = entry - address
        if code[offset:offset + 4] != original:
            raise ValueError('Unexpected pinned Thumb entry instruction')
        code[offset:offset + 4] = assembled[entry:entry + 4]
    code.extend(assembled[STUB:])
    if any(h[0] == 1 and address < h[2] < address + len(code) for h in headers):
        raise ValueError('Extended executable mapping overlaps another segment')
    # No executable padding is available. Move only the RX file image, keeping
    # every virtual address, other mapping, relocation and program-header count.
    # Match p_offset modulo page size to p_vaddr for Android's ELF loader.
    new_offset = ((len(data) + 0xfff) & ~0xfff) + (address & 0xfff)
    result = bytearray(data)
    result.extend(bytes(new_offset - len(result)))
    result.extend(code)
    header[1], header[4], header[5] = new_offset, len(code), len(code)
    struct.pack_into('<8I', result, phoff + index * phsize, *header)
    # Keep section-based disassembly pointed at the actual mapped code.
    shoff = struct.unpack_from('<I', data, 32)[0]
    shsize, shnum = struct.unpack_from('<HH', data, 46)
    if shsize != 40:
        raise ValueError('Unexpected ELF32 section-header size')
    for i in range(shnum):
        offset = shoff + i * shsize
        section = list(struct.unpack_from('<10I', data, offset))
        if section[2] & 4 and old_offset <= section[4] < old_offset + size:
            section[4] += new_offset - old_offset
            struct.pack_into('<10I', result, offset, *section)
    if hashlib.sha256(result).hexdigest() != PATCHED_SHA256:
        raise ValueError('Unexpected generated ARMv7 graphics checksum')
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'build/gralloc32-candidate')
    args = parser.parse_args()
    data = patch(args.source.read_bytes())
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'libgrallocutils.so').write_bytes(data)
    (out / 'source.json').write_text(json.dumps({
        'source_sha256': SOURCE_SHA256,
        'patched_sha256': hashlib.sha256(data).hexdigest(),
        'previous_patched_sha256': PREVIOUS_PATCHED_SHA256,
        'device_library': '/vendor/lib/libgrallocutils.so',
        'scope': 'Legacy 10-bit CAMERA_OUTPUT: PRIVATE selects codec-compatible linear VENUS P010',
        'status': 'Unvalidated ARMv7 graphics trial; matching ARM64 trial required',
    }, indent=2) + '\n')
    print(out)


if __name__ == '__main__':
    main()
