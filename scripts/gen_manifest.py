#!/usr/bin/env python3
"""Regenerate aox/manifest.json from local clones of the aox trees.

    python scripts/gen_manifest.py --trees /path/with/the/clones [--ref origin/aox]

Install rules of entries already in the manifest are kept; hashes, sizes and
DT_NEEDED lists are recomputed at the given ref. The app set is everything
under proprietary/ in vendor_oplus_camera. Files that differ between the
OnePlus 9 and 9 Pro vendor trees become one entry per device.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess

from build import elf_needed

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "aox/manifest.json"
SOURCES = {
    "camera": "vendor_oplus_camera",
    "vendor": "proprietary_vendor_oneplus_lemonade",
    "vendor_pro": "proprietary_vendor_oneplus_lemonadep",
    "device": "android_device_oneplus_lemonade",
    "hardware": "android_hardware_oplus",
    "common": "android_device_oneplus_sm8350-common",
}
APK = "system_ext/priv-app/OplusCamera/OplusCamera.apk"
# A separate OEM privileged application; the camera runs without it.
APP_SKIP = ("system_ext/priv-app/OplusAppPlatform/",)
# Libraries the 5.x app is paired with: they replace the device copy whenever
# the module's own app is the one in use.
PAIR = [
    "odm/lib64/libAlgoInterface.so",
    "odm/lib64/libAlgoProcess.so",
    "odm/lib64/libPreviewDecisionOld.so",
    "odm/lib64/libFilterWrapper.so",
]
# 5.x additions to /odm: (path, or a prefix ending in / or -, kind)
ADDED = [
    ("odm/lib64/libaideblur.so", "library"),
    ("odm/lib64/libextendfile.so", "library"),
    ("odm/lib64/libmsnativefilter.so", "library"),
    ("odm/etc/camera/meishe_lut/", "data"),
    ("odm/etc/camera/filters_lut/gt-", "data"),
    ("odm/etc/camera/selfbokehmodel.bin", "data"),
    ("odm/etc/camera/selfbokehParam.json", "data"),
]

# Changed at build time: path -> patch (scripts/patch_sdk.py, patch_hal.py).
SDK_JAR = "system_ext/framework/com.oplus.camera.unit.sdk.jar"
HAL = "vendor/lib64/hw/camera.qcom.so"

# Build inputs outside proprietary/: name -> (source, path)
INPUTS = {
    "privapp-permissions-oplus.xml": ("camera", "configs/permissions/privapp-permissions-oplus.xml"),
    "file_contexts": ("camera", "sepolicy/vendor/file_contexts"),
}


class Tree:
    def __init__(self, path, ref):
        self.path, self.ref = path, ref
        self.revision = self.git("rev-parse", ref).decode().strip()
        self.files = set(self.git("ls-tree", "-r", "--name-only", ref).decode().split("\n"))

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.path), *args], check=True,
                              capture_output=True).stdout

    def read(self, path):
        return self.git("show", f"{self.ref}:{path}")

    def url(self):
        remote = self.git("remote", "get-url", "origin").decode().strip()
        return remote.replace("git@github.com:", "https://github.com/").removesuffix(".git")


def describe(data, old):
    entry = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    if data[:4] == b"\x7fELF":
        if data[4] == 2:
            entry["needed"] = elf_needed(data)
        elif old and "needed" in old:
            # 32-bit ARM: the list is maintained by hand. Hexagon skels have none.
            entry["needed"] = old["needed"]
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trees", type=pathlib.Path, required=True)
    parser.add_argument("--ref", default="origin/aox")
    args = parser.parse_args()
    trees = {name: Tree(args.trees / directory, args.ref) for name, directory in SOURCES.items()}
    previous = json.loads(MANIFEST.read_text())
    old = {}
    for entry in previous["files"]:
        if entry.get("device", "lemonade") == "lemonade":
            old[entry["path"]] = entry
    files = []

    camera = trees["camera"]
    parts = sorted(path for path in camera.files if path.startswith("proprietary/" + APK + ".part"))
    data = b"".join(camera.read(path) for path in parts)
    files.append({"path": APK, "source": "camera", "parts": parts, "group": "app",
                  "kind": "apk", **describe(data, None)})
    for source in sorted(camera.files):
        path = source.removeprefix("proprietary/")
        if path == source or source in parts or path.startswith(APP_SKIP):
            continue
        kind = "library" if path.endswith(".so") else "data"
        files.append({"path": path, "source": "camera", "group": "app", "kind": kind,
                      **describe(camera.read(source), None)})
        if path == SDK_JAR:
            files[-1]["patch"] = "client-package"

    def vendor_entries(path, base):
        """One entry, or one per device when the two vendor trees differ."""
        blobs = {}
        for device, name in (("lemonade", "vendor"), ("lemonadep", "vendor_pro")):
            if "proprietary/" + path in trees[name].files:
                blobs[device] = (name, trees[name].read("proprietary/" + path))
        if not blobs:
            raise SystemExit(f"Not in either vendor tree: {path}")
        if len({data for _, data in blobs.values()}) == 1 and len(blobs) == 2:
            name, data = blobs["lemonade"]
            return [{"path": path, "source": name, **base, **describe(data, old.get(path))}]
        return [{"path": path, "source": name, "device": device, **base,
                 **describe(data, old.get(path))} for device, (name, data) in blobs.items()]

    for path in PAIR:
        files += vendor_entries(path, {"group": "pair", "kind": "library", "install": "pair"})
    vendor_files = sorted(path.removeprefix("proprietary/") for path in trees["vendor"].files)
    for prefix, kind in ADDED:
        for path in vendor_files:
            if path == prefix or (prefix[-1] in "/-" and path.startswith(prefix)):
                files += vendor_entries(path, {"group": "fix", "kind": kind, "install": "add"})
    # The HAL: the patched build replaces only the stock library it was made from.
    for new in vendor_entries(HAL, {"group": "fix", "kind": "library", "install": "replace",
                                    "patch": "session-key"}):
        new["replace_sha256"] = [new["sha256"]]
        files.append(new)
    listed = {entry["path"] for entry in files}
    for path, entry in old.items():
        if path in listed or entry.get("group", "fix") != "fix":
            continue
        base = {"group": "fix", "kind": entry["kind"], "install": entry["install"]}
        for new in vendor_entries(path, base):
            if "replace_sha256" in entry:
                # Device copies this change may replace: the ones accepted
                # before, plus the previously pinned build of this file.
                accepted = [*entry["replace_sha256"], entry["sha256"]]
                device = new.get("device")
                accepted += previous.get("replace_extra", {}).get(f"{device}:{path}", [])
                new["replace_sha256"] = sorted(set(accepted) - {new["sha256"]})
            files.append(new)

    inputs = []
    for name, (source, path) in INPUTS.items():
        data = trees[source].read(path)
        inputs.append({"name": name, "source": source, "src": path,
                       "sha256": hashlib.sha256(data).hexdigest()})
    inputs += [entry for entry in previous.get("inputs", []) if "url" in entry]

    manifest = {
        "branch": "aox",
        "app_version": previous.get("app_version", ""),
        "sources": {name: {"repository": tree.url(), "revision": tree.revision}
                    for name, tree in trees.items()},
        "replace_extra": previous.get("replace_extra", {}),
        "fixtures": previous.get("fixtures", {}),
        "fwk_markers": previous.get("fwk_markers", []),
        "inputs": inputs,
        "files": files,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{len(files)} files, {sum(entry['size'] for entry in files) >> 20} MiB")


if __name__ == "__main__":
    main()
