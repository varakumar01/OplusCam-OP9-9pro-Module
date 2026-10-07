#!/usr/bin/env python3
"""Prepare a source-pinned graphics format-selection trial, never a release default."""
import argparse
import hashlib
import json
import pathlib
import struct

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_SHA256 = '4bfa1e171bfac3cc6665a0a9ccc8ed93882b54fb3c412655f8d3ac494278f204'
PREVIOUS_PATCHED_SHA256 = '151e810f0a81f33dfedbb7893382993cbb2e4a0a3bc107c4c33e427414d92220'
PATCHED_SHA256 = 'd5c40595a99ee107ebbb92290f27f5e17f35ce9297db705adae2d82577c909e6'
ENTRY = 0xad74
STUB = 0xe880


def branch(pc, target, opcode=0x14000000, bits=26, shift=0):
    delta = target - pc
    if delta % 4 or not -(1 << (bits + 1)) <= delta < (1 << (bits + 1)):
        raise ValueError('Branch target outside AArch64 instruction range')
    return opcode | (((delta // 4) & ((1 << bits) - 1)) << shift)


def patch(data):
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError('Unexpected ROM graphics library; refusing an unpinned native patch')
    if data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('Expected little-endian ELF64 AArch64')
    if struct.unpack_from('<I', data, ENTRY)[0] != 0xaa0003e3:
        raise ValueError('Unexpected format-selector instruction')
    # Match PRIVATE / legacy 10-bit / CAMERA_OUTPUT. For other requests, execute
    # the displaced mov and return to the original format-selection path.
    words = [
        0xaa0003e3,  # mov x3, x0
        branch(STUB + 4, ENTRY + 4, 0x36f00003, 14, 5),  # tbz w3, #30
        branch(STUB + 8, ENTRY + 4, 0x36880003, 14, 5),  # tbz w3, #17
        0x7100883f,  # cmp w1, #34
        branch(STUB + 16, ENTRY + 4, 0x54000001, 19, 5),  # b.ne
        0x52818140,  # mov w0, #0xc0a
        0x72aff460,  # movk w0, #0x7fa3, lsl #16: Qualcomm linear P010
        branch(STUB + 28, 0xada4),  # original function epilogue
    ]
    # The vendor P010 path already supplies the required 32-line alignment.
    payload = struct.pack('<8I', *words)
    if data[STUB:STUB + len(payload)] != bytes(len(payload)):
        raise ValueError('Expected unused zero-filled executable-segment padding')
    result = bytearray(data)
    phoff = struct.unpack_from('<Q', data, 32)[0]
    entsize, count = struct.unpack_from('<HH', data, 54)
    if entsize != 56:
        raise ValueError('Unexpected ELF program-header size')
    candidates = []
    for i in range(count):
        offset = phoff + i * entsize
        h = list(struct.unpack_from('<IIQQQQQQ', data, offset))
        if h[0] == 1 and h[1] == 5 and h[2] == h[3] and h[2] + h[5] == STUB:
            candidates.append((offset, h))
    if len(candidates) != 1:
        raise ValueError('Expected one RX segment ending at the pinned code cave')
    offset, h = candidates[0]
    h[5] += len(payload)
    h[6] += len(payload)
    if any(struct.unpack_from('<IIQQQQQQ', data, phoff + i * entsize)[0] == 1
           and STUB < struct.unpack_from('<IIQQQQQQ', data, phoff + i * entsize)[3] < STUB + len(payload)
           for i in range(count)):
        raise ValueError('Extended executable mapping would overlap another segment')
    struct.pack_into('<IIQQQQQQ', result, offset, *h)
    struct.pack_into('<I', result, ENTRY, branch(ENTRY, STUB))
    result[STUB:STUB + len(payload)] = payload
    if hashlib.sha256(result).hexdigest() != PATCHED_SHA256:
        raise ValueError('Unexpected generated graphics patch checksum')
    return bytes(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=pathlib.Path, required=True)
    parser.add_argument('--output-dir', type=pathlib.Path,
                        default=ROOT / 'build/gralloc-candidate')
    args = parser.parse_args()
    data = patch(args.source.read_bytes())
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'libgrallocutils.so').write_bytes(data)
    (out / 'source.json').write_text(json.dumps({
        'source_sha256': SOURCE_SHA256,
        'patched_sha256': hashlib.sha256(data).hexdigest(),
        'previous_patched_sha256': PREVIOUS_PATCHED_SHA256,
        'device_library': '/vendor/lib64/libgrallocutils.so',
        'scope': 'Legacy 10-bit CAMERA_OUTPUT: PRIVATE selects codec-compatible linear VENUS P010',
        'status': 'Unvalidated graphics trial; requires matching source and a reboot',
    }, indent=2) + '\n')
    print(out)


if __name__ == '__main__':
    main()
