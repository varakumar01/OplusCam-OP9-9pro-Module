#!/usr/bin/env python3
"""Relabel copies of existing camera libraries for app-side loading.

No filesystem partitions or SELinux allow rules are changed. Live bind mounts
are temporary until reboot; collected copies can also be included in a module.
"""
import argparse
import hashlib
import json
import pathlib
import re
import shlex
import subprocess

from device import ROOT, adb, root

CACHE = ROOT / ".cache/device/vendor_camera"
MANIFEST = CACHE / "manifest.json"
EXTRA_LIBRARIES = {
    "/odm/lib64/lib_oplus_starburst_capture.so",
    "/odm/lib64/lib_oplus_starburst_preview.so",
    # APS PF v1 resolves PFC_SetParam/PFC_AutoCorrectPreset at capture time.
    # This firmware ships the library with a vendor_file label, which the
    # camera app cannot use. Keep its code unchanged, as with starburst.
    "/odm/lib64/libPerfectlyClearCruxOpt.so",
}
EIS_LIBRARIES = {
    # A separate trial: clearing this loading error exposed another fault.
    # Do not include it in normal collections before recording is validated.
    "/vendor/lib64/libui.so",
}
# These have separate, pinned donor preparation/provenance in the builder.
# Once the module is mounted, they also appear under /odm; collecting them
# again would incorrectly describe donor or patched binaries as firmware.
DONOR_LIBRARIES = {
    "/odm/lib64/lib2DSlender.so",
    "/odm/lib64/libAncHumBokeh.so",
    "/odm/lib64/libFilterWrapper.so",
    "/odm/lib64/libancbase_rt_bokeh.so",
}


def collect(include_eis=False):
    rules = ROOT / ".cache/donor/op9/sepolicy/vendor/file_contexts"
    patterns = [re.compile(line.split()[0]) for line in rules.read_text().splitlines()
                if line.strip() and not line.startswith("#") and "same_process_hal_file" in line]
    result = root("find /odm/lib64 /vendor/lib64 -type f -name '*.so'")
    extra = EXTRA_LIBRARIES | (EIS_LIBRARIES if include_eis else set())
    candidates = [p for p in result.stdout.splitlines()
                  if p not in DONOR_LIBRARIES
                  and (p in extra or any(r.fullmatch(p) for r in patterns))]
    result = root("ls -lZ " + " ".join(shlex.quote(p) for p in candidates))
    labels = {line.split()[-1]: next((x for x in line.split() if x.startswith("u:object_r:")), "")
              for line in result.stdout.splitlines()}
    entries = []
    for remote in candidates:
        if labels.get(remote) not in ("u:object_r:vendor_file:s0", "u:object_r:same_process_hal_file:s0"):
            continue
        local = CACHE / remote.lstrip("/")
        if not local.exists():
            result = subprocess.run(["adb", "exec-out", "su", "-c", "cat " + shlex.quote(remote)],
                                    capture_output=True, check=True, timeout=60)
            if not result.stdout.startswith(b"\x7fELF"):
                raise SystemExit(f"Could not read ELF binary: {remote}")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(result.stdout)
        entries.append({"path": remote, "original_label": labels[remote],
                        "label": "u:object_r:same_process_hal_file:s0",
                        "sha256": hashlib.sha256(local.read_bytes()).hexdigest(),
                        "size": local.stat().st_size})
    MANIFEST.write_text(json.dumps(entries, indent=2) + "\n")
    print(f"Collected {len(entries)} camera libraries, {sum(x['size'] for x in entries)} bytes")


def apply():
    entries = json.loads(MANIFEST.read_text())
    for entry in entries:
        path = entry["path"]
        if not path.startswith(("/odm/lib64/", "/vendor/lib64/")) or ".." in path:
            raise SystemExit(f"Invalid path: {path}")
        local = CACHE / path.lstrip("/")
        if hashlib.sha256(local.read_bytes()).hexdigest() != entry["sha256"]:
            raise SystemExit(f"Checksum mismatch: {path}")
    adb("push", str(CACHE / "odm"), "/data/local/tmp/ooscamera-native-odm")
    if (CACHE / "vendor").exists():
        adb("push", str(CACHE / "vendor"), "/data/local/tmp/ooscamera-native-vendor")
    commands = ["mkdir -p /data/adb/ooscamera-native"]
    for entry in entries:
        path = entry["path"]
        source = "/data/local/tmp/ooscamera-native-" + path.split("/")[1] + "/" + "/".join(path.split("/")[2:])
        copy = "/data/adb/ooscamera-native" + path
        commands += [f"mkdir -p {shlex.quote(str(pathlib.PurePosixPath(copy).parent))}",
                     f"cp {shlex.quote(source)} {shlex.quote(copy)}",
                     f"chmod 0644 {shlex.quote(copy)}",
                     f"chcon u:object_r:same_process_hal_file:s0 {shlex.quote(copy)}",
                     f"/data/adb/ksu/bin/busybox nsenter -t 1 -m /system/bin/mount --bind {shlex.quote(copy)} {shlex.quote(path)}"]
    result = root("set -e; " + "; ".join(commands), timeout=180)
    print(result.stdout)
    print(f"Applied {len(entries)} reversible camera-library mounts")


def undo():
    entries = json.loads(MANIFEST.read_text())
    for entry in reversed(entries):
        result = root("/data/adb/ksu/bin/busybox nsenter -t 1 -m /system/bin/umount " + shlex.quote(entry["path"]), check=False)
        if result.returncode:
            print(result.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["collect", "apply", "undo"])
    parser.add_argument("--experimental-eis-access", action="store_true",
                        help="Collect the unvalidated vendor libui dependency trial")
    args = parser.parse_args()
    if args.experimental_eis_access and args.command != "collect":
        parser.error("--experimental-eis-access is only valid with collect")
    if args.command == "collect":
        collect(args.experimental_eis_access)
    else:
        {"apply": apply, "undo": undo}[args.command]()
