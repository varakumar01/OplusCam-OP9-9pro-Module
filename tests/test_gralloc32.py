#!/usr/bin/env python3
"""Emulate the real Thumb selector and native alignment paths, including ELF mappings."""
import argparse
from itertools import product
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
                              UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10,
                              UC_ARM_REG_R11, UC_ARM_REG_LR, UC_ARM_REG_PC,
                              UC_ARM_REG_SP)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from patch_gralloc32 import patch


def headers(data):
    offset = struct.unpack_from('<I', data, 28)[0]
    size, count = struct.unpack_from('<HH', data, 42)
    return [struct.unpack_from('<8I', data, offset + i * size) for i in range(count)]


def emulator(data):
    uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    uc.mem_map(0, 0x30000)
    for h in headers(data):
        if h[0] == 1:
            uc.mem_write(h[2], data[h[1]:h[1] + h[4]])
    uc.reg_write(UC_ARM_REG_SP, 0x2ff00)
    return uc


def execute(data, usage, fmt):
    uc = emulator(data)
    for reg, value in [(UC_ARM_REG_R0, usage & 0xffffffff),
                       (UC_ARM_REG_R1, usage >> 32), (UC_ARM_REG_R2, fmt),
                       (UC_ARM_REG_LR, 0x18001)]:
        uc.reg_write(reg, value)

    def intercept(machine, address, size, user):
        if address in (0xa7d0, 0xaa30):
            machine.reg_write(UC_ARM_REG_R0, 0)
            machine.reg_write(UC_ARM_REG_PC, machine.reg_read(UC_ARM_REG_LR))
    uc.hook_add(UC_HOOK_CODE, intercept)
    uc.emu_start(0x7d79, 0x18000, count=200)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x18000, 'Selector did not return'
    assert uc.reg_read(UC_ARM_REG_SP) == 0x2ff00, 'Selector did not restore stack'
    return uc.reg_read(UC_ARM_REG_R0)


def alignment(data, usage, fmt, width, height):
    uc = emulator(data)
    uc.mem_write(0x20000, struct.pack('<IIIIQ', width, height, fmt, 0, usage))
    for reg, value in [(UC_ARM_REG_R0, 0x20000), (UC_ARM_REG_R1, 0x21000),
                       (UC_ARM_REG_R2, 0x21004), (UC_ARM_REG_R9, 0x21000),
                       (UC_ARM_REG_R8, 0x21004), (UC_ARM_REG_R11, width),
                       (UC_ARM_REG_R10, height), (UC_ARM_REG_LR, 0x18001)]:
        uc.reg_write(reg, value)
    uc.emu_start(0x6051, 0x6054, count=100)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x6054
    assert uc.reg_read(UC_ARM_REG_R0) == 0x20000
    assert uc.reg_read(UC_ARM_REG_SP) == 0x2ff00
    # Existing native P010 width helper and output writes, without unrelated
    # external UBWC capability queries or unrelocated global stack canaries.
    uc.emu_start(0x62dd if fmt == 0x7fa30c0a else 0x6305, 0x633e, count=100)
    assert uc.reg_read(UC_ARM_REG_PC) == 0x633e
    return struct.unpack('<II', uc.mem_read(0x21000, 8))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    original = args.source.read_bytes()
    fixed = patch(original)
    before, after = headers(original), headers(fixed)
    assert len(before) == len(after) == 10
    for a, b in zip(before, after):
        if a[0] == 1 and a[6] == 5:
            assert a[0] == b[0] and a[2:4] == b[2:4] and a[6:] == b[6:]
            assert b[1] % b[7] == b[2] % b[7]
            assert b[4] == b[5] and a[4] < b[4] < a[4] + 128
            old_code = original[a[1]:a[1] + a[4]]
            new_code = bytearray(fixed[b[1]:b[1] + a[4]])
            for entry in (0x7d8c,):
                pos = entry - a[2]
                new_code[pos:pos + 4] = old_code[pos:pos + 4]
            assert bytes(new_code) == old_code, 'Unrelated code changed'
        else:
            assert a == b, 'Unrelated program header changed'
            if a[0] == 1 and a[1] != 0:
                assert original[a[1]:a[1] + a[4]] == fixed[a[1]:a[1] + a[4]]
    count = changed = 0
    for fmt, flags in product([1, 17, 34, 35, 54], product([0, 1], repeat=6)):
        usage = 0x103 | sum(value << bit for value, bit in
                            zip(flags, [30, 17, 16, 28, 49, 18]))
        a, b = execute(original, usage, fmt), execute(fixed, usage, fmt)
        if fmt == 34 and usage & 0x40020000 == 0x40020000:
            assert b == 0x7fa30c0a, (hex(usage), fmt, b)
            changed += a != b
        else:
            assert a == b, (hex(usage), fmt, a, b)
        count += 1
    cases = 0
    for fmt, flags, dimensions in product([54, 55, 0x7fa30c0a], product([0, 1], repeat=6),
                                         [(1920, 822), (3840, 1644), (1280, 720),
                                          (1921, 823), (1920, 0x7fffffff)]):
        usage = 0x103 | sum(value << bit for value, bit in
                            zip(flags, [30, 17, 16, 28, 49, 18]))
        a, b = alignment(original, usage, fmt, *dimensions), alignment(fixed, usage, fmt, *dimensions)
        assert a == b, (hex(usage), fmt, a, b)
        cases += 1
    assert alignment(fixed, 0x40020103, 0x7fa30c0a, 1920, 822) == (1920, 832)
    assert alignment(fixed, 0x50030022, 0x7fa30c0a, 3840, 1644) == (3840, 1664)
    print(f'ARMv7 ELF layout and selector: {count} cases, {changed} corrected; '
          f'alignment: {cases} cases passed; stack preserved.')


if __name__ == '__main__':
    main()
