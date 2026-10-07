#!/usr/bin/env python3
"""Emulate the pinned format selector; run with uv run --with unicorn."""
import argparse
from itertools import product
from pathlib import Path
import sys
import struct

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (
    UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X30,
    UC_ARM64_REG_SP, UC_ARM64_REG_PC, UC_ARM64_REG_X19, UC_ARM64_REG_X20,
    UC_ARM64_REG_X21, UC_ARM64_REG_X22, UC_ARM64_REG_X23, UC_ARM64_REG_X24,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from patch_gralloc import patch


def execute(data, usage, fmt):
    emulator = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    emulator.mem_map(0, 0x20000)
    emulator.mem_write(0, data)
    emulator.mem_map(0x2f0000, 0x10000)
    emulator.reg_write(UC_ARM64_REG_SP, 0x2fff00)
    emulator.reg_write(UC_ARM64_REG_X0, usage)
    emulator.reg_write(UC_ARM64_REG_X1, fmt)

    def intercept(uc, address, size, user):
        # Invalid-format diagnostics call the logging PLT stub. Simulate its
        # return without replacing any format-selection instructions.
        if address == 0xe590:
            uc.reg_write(UC_ARM64_REG_X0, 0)
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_X30))

    emulator.hook_add(UC_HOOK_CODE, intercept)
    emulator.reg_write(UC_ARM64_REG_X30, 0x100000)
    emulator.emu_start(0xad60, 0x100000, count=100)
    assert emulator.reg_read(UC_ARM64_REG_PC) == 0x100000, 'Selector did not return'
    return emulator.reg_read(UC_ARM64_REG_X0) & 0xffffffff


def execute_alignment(data, usage, fmt, width, height):
    emulator = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    emulator.mem_map(0, 0x20000)
    emulator.mem_write(0, data)
    emulator.mem_map(0x2f0000, 0x10000)
    emulator.reg_write(UC_ARM64_REG_SP, 0x2fff00)
    for register, value in [
        (UC_ARM64_REG_X19, 0x10004), (UC_ARM64_REG_X20, 0x10000),
        (UC_ARM64_REG_X21, height), (UC_ARM64_REG_X22, width),
        (UC_ARM64_REG_X23, fmt), (UC_ARM64_REG_X24, usage),
    ]:
        emulator.reg_write(register, value)
    emulator.emu_start(0x88c4 if fmt == 0x7fa30c0a else 0x8880, 0x891c, count=100)
    assert emulator.reg_read(UC_ARM64_REG_PC) == 0x891c, 'Alignment path did not finish'
    return struct.unpack('<II', emulator.mem_read(0x10000, 8))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    original = args.source.read_bytes()
    fixed = patch(original)
    changed = count = 0
    for fmt, flags in product([1, 17, 34, 35, 54], product([0, 1], repeat=6)):
        usage = 0x103 | sum(value << bit for value, bit in
                            zip(flags, [30, 17, 16, 28, 49, 18]))
        before = execute(original, usage, fmt)
        after = execute(fixed, usage, fmt)
        matching_camera_request = fmt == 34 and usage & 0x40020000 == 0x40020000
        if matching_camera_request:
            expected = 0x7fa30c0a
            assert after == expected, (hex(usage), fmt, hex(after))
            changed += before != after
        else:
            assert before == after, (hex(usage), fmt, before, after)
        count += 1
    alignment_cases = 0
    for fmt, flags, dimensions in product(
        [54, 55, 0x7fa30c0a], product([0, 1], repeat=6),
        [(1920, 822), (3840, 1644), (1280, 720), (1921, 823),
         (1920, 0x7fffffff)],
    ):
        usage = 0x103 | sum(value << bit for value, bit in
                            zip(flags, [30, 17, 16, 28, 49, 18]))
        before = execute_alignment(original, usage, fmt, *dimensions)
        after = execute_alignment(fixed, usage, fmt, *dimensions)
        assert before == after, (hex(usage), fmt, before, after)
        alignment_cases += 1
    assert execute_alignment(fixed, 0x40020103, 0x7fa30c0a, 1920, 822) == (1920, 832)
    assert execute_alignment(fixed, 0x50030022, 0x7fa30c0a, 3840, 1644) == (3840, 1664)
    assert 1920 * 832 * 3 == 4792320
    assert 3840 * 1664 * 3 == 19169280
    print(f'AArch64 alignment verification: {alignment_cases} cases passed.')
    print(f'AArch64 selector verification: {count} cases; {changed} corrected '
          'legacy camera cases; all other outputs identical.')


if __name__ == '__main__':
    main()
