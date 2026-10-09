#!/usr/bin/env python3
"""Make com.oplus.packageName a session key of the OnePlus 9 camera HAL.

camera.qcom.so builds android.request.availableSessionKeys in two places,
each adding four com.oplus tags by name. cameraserver drops every session
parameter that is not in that list, so only a cameraserver built with
soong config camera.package_name could give the HAL the client package name,
and without it the HAL does not run Night, Long exposure, XPan or Dual-view
video. This repoints the factory key engineercamera.agingtest.mode.select at
the packageName string; patch_sdk.py makes the camera send the tag.

    python scripts/patch_hal.py camera.qcom.so patched.so
"""
import struct
import sys

OLD = b"engineercamera.agingtest.mode.select\0"
NEW = b"\0packageName\0"


def patch(data):
    """Return the patched library. File offsets equal addresses in this
    library's .text and .rodata, which the checks below rely on."""
    data = bytearray(data)
    if data.count(OLD) != 1 or NEW not in data:
        raise SystemExit("camera.qcom.so: session key strings not found")
    old, new = data.index(OLD), data.index(NEW) + 1
    edits = 0
    # adrp x1, old@page ; add x2, .. ; mov x0, .. ; add x1, x1, old@pageoff
    for pc in range(0, len(data) - 16, 4):
        adrp, add = struct.unpack_from("<I", data, pc)[0], struct.unpack_from("<I", data, pc + 12)[0]
        if add != (0x91000021 | (old & 0xfff) << 10) or adrp & 0x9f00001f != 0x90000001:
            continue
        imm = (adrp >> 5 & 0x7ffff) << 2 | adrp >> 29 & 3
        imm -= (imm & 0x100000) << 1
        if (pc & ~0xfff) + (imm << 12) != old & ~0xfff:
            continue
        delta = ((new & ~0xfff) - (pc & ~0xfff)) >> 12
        struct.pack_into("<I", data, pc, 0x90000001 | (delta & 3) << 29 | (delta >> 2 & 0x7ffff) << 5)
        struct.pack_into("<I", data, pc + 12, 0x91000021 | (new & 0xfff) << 10)
        edits += 1
    if edits != 2:
        raise SystemExit(f"camera.qcom.so: expected 2 session key sites, found {edits}")
    return bytes(data)


if __name__ == "__main__":
    with open(sys.argv[1], "rb") as source, open(sys.argv[2], "wb") as target:
        target.write(patch(source.read()))
