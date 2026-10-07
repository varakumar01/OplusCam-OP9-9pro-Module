#!/usr/bin/env python3
"""Package a pinned OP9 donor as a KernelSU Next module, without boot-JAR edits."""
import argparse
import hashlib
import json
import pathlib
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import urllib.request

from prepare_retouch import (REPOSITORY as RETOUCH_REPOSITORY,
                             REVISION as RETOUCH_REVISION,
                             SOURCE_SHA256 as RETOUCH_SHA256)
from patch_gralloc import (SOURCE_SHA256 as GRALLOC_SOURCE_SHA256,
                           PATCHED_SHA256 as GRALLOC_PATCHED_SHA256,
                           PREVIOUS_PATCHED_SHA256 as GRALLOC_PREVIOUS_SHA256)
from patch_gralloc32 import (SOURCE_SHA256 as GRALLOC32_SOURCE_SHA256,
                            PATCHED_SHA256 as GRALLOC32_PATCHED_SHA256,
                            PREVIOUS_PATCHED_SHA256 as GRALLOC32_PREVIOUS_SHA256)

ROOT = pathlib.Path(__file__).resolve().parents[1]
DONOR_REVISION = "6e7d1e0bb6b242cf58ae152152d011e846bf812e"
APK_SHA256 = "7b9c86eab1276809c2661add2cf860e23bed1dc42f1333d95118578ad7985b12"
FILTER_REPOSITORY = "https://github.com/TheMuppets/proprietary_vendor_oneplus_salami"
FILTER_REVISION = "2ae5c2548d5150b9948ddec33f9b5bbb2f07fd66"
FILTER_LIBRARIES = {
    "libFilterWrapper.so": "62e86d478bb4554f510e9495ccb971f0c1e07ef802227c3e87787e13fc4cf049",
}
BLUR_REPOSITORY = "https://github.com/resist15/vendor_realme_porsche"
BLUR_REVISION = "8bdc52979f0fe9f424a92b62b7bf0c72e52b4c76"
BLUR_LIBRARIES = {
    "libAncHumBokeh.so": "472d2d541b366f6472df730a3aa892963150b5b969db1e46c8ad83429c00058c",
    "libancbase_rt_bokeh.so": "146849c76ffb46fcfe0af5cac25fe32973de5d2d649837a10dcca362ca9c961d",
}
BLUR_LOADER_SHA256 = "0aa99b3f111dea8bc12e5e5500fe37e29d0191d656881fc96ff9bf123492a255"
FRONT_BLUR_SHA256 = "1dd65d4ed2da2dea9a7f11d5887c80d15e7d258c9a492ac1c2f2b2a279c41c0a"
CAMERA_SDK_SHA256 = "4ee8f097d63d9766bafba1bf9a3073363443ad5fa007f2f9ce83005cb3c461b5"
AOX_CAM4_MANIFEST = ROOT / "aox-cam4/manifest.json"
UAH_CLIENT_PATH = "odm/lib64/liboplus-uah-client.so"
UAH_CLIENT_MARKER = b"ooscamera-aox-cam4-uah-client"
UAH_CLIENT_SYMBOLS = [
    "UahEventAcquireWrapper", "UahRelease", "UahReleaseWapper", "setRelatedSysInfo", "uahInit",
    "UahNotifyWapper", "UahNotify", "UahEventAcquire", "UahEventAcquireOneWay", "UahResAcquire",
    "UahPlatformResAcquire", "UahResStateRequest", "UahMutiResStateRequest", "UahGetHistory",
    "UahGetPowerConsis", "UahGetPMStatus", "Uah_fetch_dataset", "uahRuleCtl", "UahResourceInfo",
]


def repair_front_blur_headers(data):
    """Map an explicit PT_PHDR for the pinned donor's relocated ELF headers.

    Modern Android rejects this donor because its program-header table has a
    different file/virtual offset and no PT_PHDR. Append a correctly mapped
    table to the final data segment; executable bytes remain untouched.
    """
    if hashlib.sha256(data).hexdigest() != FRONT_BLUR_SHA256:
        raise SystemExit("Unexpected front portrait JNI source")
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise SystemExit("Expected ELF64 little-endian AArch64 front portrait JNI")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    if phsize != 56 or phoff + phnum * phsize > len(data):
        raise SystemExit("Invalid front portrait program-header table")
    headers = [list(struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize))
               for i in range(phnum)]
    if any(h[0] == 6 for h in headers):
        raise SystemExit("Front portrait JNI already has PT_PHDR")
    tail = max((h for h in headers if h[0] == 1), key=lambda h: h[2])
    if tail[5] != tail[6] or tail[2] + tail[5] != len(data) or tail[1] != 6:
        raise SystemExit("Expected final writable data segment without BSS")
    offset = (len(data) + 7) & ~7
    size = (phnum + 1) * phsize
    address = tail[3] + offset - tail[2]
    tail[5] = tail[6] = offset + size - tail[2]
    headers.append([6, 4, offset, address, address, size, size, 8])
    result = bytearray(data)
    result.extend(bytes(offset - len(result)))
    for header in headers:
        result.extend(struct.pack("<IIQQQQQQ", *header))
    struct.pack_into("<Q", result, 32, offset)
    struct.pack_into("<H", result, 56, phnum + 1)
    return bytes(result)


def patch_blur_libraries(core, loader):
    """Isolate blur's SNPE loader and request GPU_FLOAT16 through its normal check.

    The firmware loader otherwise requests unavailable DSP execution and falls
    back to CPU, giving approximately 7 fps. Other users of libsnpe_loader keep
    their original library. Fixed-length edits preserve all offsets/segments.
    """
    if hashlib.sha256(core).hexdigest() != BLUR_LIBRARIES["libAncHumBokeh.so"]:
        raise SystemExit("Unexpected blur engine source")
    if hashlib.sha256(loader).hexdigest() != BLUR_LOADER_SHA256:
        raise SystemExit("Unexpected firmware SNPE loader source")
    old, new = b"libsnpe_loader.so\0", b"liboosb_loader.so\0"
    if core.count(old) != 1 or loader.count(old) != 1 or len(old) != len(new):
        raise SystemExit("Expected one fixed-length loader name in each blur library")
    result = bytearray(loader)
    # Pinned ELF64 AArch64 instruction: mov w19, w0 -> mov w19, #3.
    # The existing isRuntimeAvailable check and CPU fallback remain intact.
    if result[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", result, 18)[0] != 183:
        raise SystemExit("Expected an AArch64 SNPE loader")
    if struct.unpack_from("<I", result, 0x2804)[0] != 0x2A0003F3:
        raise SystemExit("Unexpected SNPE runtime selection instruction")
    struct.pack_into("<I", result, 0x2804, 0x52800073)
    return core.replace(old, new), bytes(result).replace(old, new)


def remove_alog_dependency(data):
    """Remove one unused DT_NEEDED entry without moving any ELF code or segments.

    The pinned wrapper imports no alog symbols. Loading that library starts an
    OEM background logger that can outlive its mapping when APS reloads filters.
    """
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise SystemExit("Expected an ELF64 little-endian AArch64 filter wrapper")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    headers = [struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize)
               for i in range(phnum)]
    dynamic = next(h for h in headers if h[0] == 2)
    entries = []
    for offset in range(dynamic[2], dynamic[2] + dynamic[5], 16):
        tag, value = struct.unpack_from("<qQ", data, offset)
        entries.append((offset, tag, value))
        if tag == 0:
            break
    straddr = next(value for _, tag, value in entries if tag == 5)
    segment = next(h for h in headers if h[0] == 1 and h[3] <= straddr < h[3] + h[5])
    stroff = segment[2] + straddr - segment[3]
    matches = [offset for offset, tag, value in entries if tag == 1
               and data[stroff + value:data.index(b"\0", stroff + value)] == b"libalog.so"]
    if len(matches) != 1:
        raise SystemExit("Expected exactly one unused libalog dependency")
    start, end = matches[0], entries[-1][0] + 16
    result = bytearray(data)
    result[start:end] = data[start + 16:end] + bytes(16)
    return bytes(result)


def elf_needed(data):
    """DT_NEEDED names of an ELF64 little-endian AArch64 shared library."""
    if data[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", data, 18)[0] != 183:
        raise SystemExit("Expected an ELF64 little-endian AArch64 library")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    headers = [struct.unpack_from("<IIQQQQQQ", data, phoff + i * phsize) for i in range(phnum)]
    dynamic = next(h for h in headers if h[0] == 2)
    entries = []
    for offset in range(dynamic[2], dynamic[2] + dynamic[5], 16):
        tag, value = struct.unpack_from("<qQ", data, offset)
        if tag == 0:
            break
        entries.append((tag, value))
    straddr = next(value for tag, value in entries if tag == 5)
    segment = next(h for h in headers if h[0] == 1 and h[3] <= straddr < h[3] + h[5])
    stroff = segment[2] + straddr - segment[3]
    return [data[stroff + value:data.index(b"\0", stroff + value)].decode()
            for tag, value in entries if tag == 1]


def aox_cam4_target(stage, path):
    """Module payload path of a device path (odm/... or vendor/...)."""
    parts = pathlib.PurePosixPath(path).parts
    if ".." in parts or parts[0] not in ("odm", "vendor"):
        raise SystemExit(f"Invalid aox-cam4 path: {path}")
    # /odm is staged under the vendor tree, as for the donor payload.
    return stage / "system/vendor" / path if parts[0] == "odm" else stage / "system" / path


def stage_aox_cam4(stage, cache, uah_client):
    """Stage the aox-cam4 camera libraries and the on-device edit data.

    Files the module already provides (its own pinned sources, or libraries
    collected from the device) are left untouched. customize.sh decides on
    the device which staged libraries apply (aox-cam4/files.txt).
    """
    manifest = json.loads(AOX_CAM4_MANIFEST.read_text())
    source = json.loads((cache / "source.json").read_text())
    if source.get("revision") != manifest["revision"]:
        raise SystemExit("aox-cam4 cache was prepared for a different revision")
    lines, labels, staged, provided = [], [], {}, []
    for entry in manifest["files"]:
        target = aox_cam4_target(stage, entry["path"])
        if entry["path"] in manifest["module_owned"] or target.exists():
            provided.append(entry["path"])
            continue
        data = (cache / entry["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SystemExit(f"aox-cam4 checksum mismatch: {entry['path']}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        staged[entry["path"]] = entry["sha256"]
        lines.append("|".join([entry["path"], entry["install"], entry["sha256"],
                               ",".join(entry.get("replace_sha256", [])),
                               ",".join(entry.get("needed", []))]))
        if entry["kind"] == "library":
            labels.append(str(target.relative_to(stage)))
    if uah_client:
        data = uah_client.read_bytes()
        needed = elf_needed(data)
        if UAH_CLIENT_MARKER not in data or not set(needed) <= {"libc.so", "libdl.so"}:
            raise SystemExit("Unexpected liboplus-uah-client build; use native/uah-client/build.sh")
        if any(symbol.encode() + b"\0" not in data for symbol in UAH_CLIENT_SYMBOLS):
            raise SystemExit("liboplus-uah-client is missing a stock entry point")
        target = aox_cam4_target(stage, UAH_CLIENT_PATH)
        if target.exists():
            provided.append(UAH_CLIENT_PATH)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            digest = hashlib.sha256(data).hexdigest()
            staged[UAH_CLIENT_PATH] = digest
            lines.append("|".join([UAH_CLIENT_PATH, "uah", digest, "", ",".join(needed)]))
            labels.append(str(target.relative_to(stage)))
    data_dir = stage / "aox-cam4"
    shutil.copytree(ROOT / "module/aox-cam4", data_dir)
    (data_dir / "files.txt").write_text(
        "# path|rule|sha256|replace sha256s|needed (generated by build.py)\n"
        + "".join(line + "\n" for line in lines))
    with (stage / "native-labels.txt").open("a") as handle:
        handle.write("".join(label + "\n" for label in labels))
    for name in ("aox-cam4.sh", "sepolicy.rule"):
        shutil.copyfile(ROOT / "module" / name, stage / name)
    (stage / "aox-cam4-source.json").write_text(json.dumps({
        key: manifest[key] for key in (
            "repository", "branch", "revision", "base_revision", "window",
            "device_repository", "device_revision", "hardware_repository",
            "hardware_revision", "common_repository", "common_revision")
    } | {"files": staged, "module_provided": provided,
         "edits": "aox-cam4/edits.txt, applied on the device at install time"},
        indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--donor", type=pathlib.Path, default=ROOT / ".cache/donor/op9")
    parser.add_argument("--apk", type=pathlib.Path, help="Use a locally patched and signed camera APK")
    parser.add_argument("--sdk", type=pathlib.Path, help="Use the patched app-scoped camera SDK")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "build")
    parser.add_argument("--candidate-version", help="Explicit prerelease version for an unvalidated test module")
    parser.add_argument("--retouch-cache", type=pathlib.Path,
                        help="Prepared native Retouch candidate; requires --candidate-version")
    parser.add_argument("--gralloc-cache", type=pathlib.Path,
                        help="Source-pinned graphics selector trial; requires --candidate-version")
    parser.add_argument("--gralloc32-cache", type=pathlib.Path,
                        help="Matching ARMv7 graphics trial; requires --gralloc-cache")
    parser.add_argument("--visibility-cache", type=pathlib.Path,
                        help="Experimental automatic KernelSU setup; requires --candidate-version")
    parser.add_argument("--native-cache", type=pathlib.Path, help="Verified libraries collected from this phone")
    parser.add_argument("--camera-config", type=pathlib.Path, help="Device camera configuration override")
    parser.add_argument("--filter-cache", type=pathlib.Path,
                        help="Cache/fetch pinned OEM capture-filter libraries")
    parser.add_argument("--blur-cache", type=pathlib.Path,
                        help="Cache/fetch pinned video blur engine; requires native cache")
    parser.add_argument("--aox-cam4-cache", type=pathlib.Path,
                        help="aox-cam4 camera changes prepared by prepare_aox_cam4.py")
    parser.add_argument("--uah-client", type=pathlib.Path,
                        help="liboplus-uah-client.so from native/uah-client/build.sh; requires --aox-cam4-cache")
    args = parser.parse_args()
    if args.uah_client and not args.aox_cam4_cache:
        raise SystemExit("--uah-client requires --aox-cam4-cache")
    if args.visibility_cache and not args.candidate_version:
        raise SystemExit("Automatic profile setup requires --candidate-version until validated")
    if args.candidate_version and not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*-[A-Za-z0-9.-]+", args.candidate_version):
        raise SystemExit("Candidate version must include a prerelease suffix")
    if args.retouch_cache and not args.candidate_version:
        raise SystemExit("The unvalidated Retouch library requires --candidate-version")
    if args.gralloc_cache and not args.candidate_version:
        raise SystemExit("The graphics trial requires --candidate-version")
    if args.gralloc32_cache and not args.gralloc_cache:
        raise SystemExit("The ARMv7 graphics trial requires its ARM64 counterpart")
    film_guard = False
    if args.apk:
        with zipfile.ZipFile(args.apk) as archive:
            film_guard = any(b"ooscameraGuardFilmOptions" in archive.read(name)
                             for name in archive.namelist()
                             if re.fullmatch(r"classes\d*\.dex", name))
        if film_guard and not (args.candidate_version and args.gralloc_cache and args.gralloc32_cache):
            raise SystemExit("The Film LOG option guard requires the paired graphics test build")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    donor = args.donor.resolve()
    revision = subprocess.check_output(["git", "-C", str(donor), "rev-parse", "HEAD"], text=True).strip()
    if revision != DONOR_REVISION:
        raise SystemExit(f"Unexpected donor revision: {revision}")
    source = donor / "proprietary"
    apk = source / "system_ext/priv-app/OplusCamera/OplusCamera.apk"
    if not apk.exists():
        parts = sorted(apk.parent.glob("OplusCamera.part*"))
        if not parts:
            raise SystemExit("Donor APK parts missing")
        with apk.open("wb") as out:
            for part in parts:
                out.write(part.read_bytes())
    if hashlib.sha256(apk.read_bytes()).hexdigest() != APK_SHA256:
        raise SystemExit("Donor camera APK hash mismatch")
    with zipfile.ZipFile(apk) as archive:
        if archive.testzip():
            raise SystemExit("Donor camera APK contains a damaged ZIP entry")

    stage = output_dir / "module"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for path in source.rglob("*"):
        if not path.is_file() or ".part" in path.name:
            continue
        relative = path.relative_to(source)
        # AppPlatform is a separate OEM privileged application; add it only if
        # camera failures demonstrate that it is necessary on this build.
        if "OplusAppPlatform" in relative.parts:
            continue
        if relative.parts[0] == "odm":
            target = stage / "system/vendor/odm" / pathlib.Path(*relative.parts[1:])
        elif relative.parts[0] == "system":
            target = stage / relative
        else:
            target = stage / "system" / relative
        if path.read_bytes().startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise SystemExit(f"Unresolved LFS pointer: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    if args.apk:
        with zipfile.ZipFile(args.apk) as archive:
            if archive.testzip():
                raise SystemExit("Patched APK is damaged")
        shutil.copyfile(args.apk, stage / "system/system_ext/priv-app/OplusCamera/OplusCamera.apk")

    # The Qualcomm SDK requests the platform suffix on Android 12 and newer.
    # Package a repaired alias instead of modifying the shared SDK or firmware.
    front_jni = source / "system_ext/lib64/libjnisingleblur_api.so"
    (stage / "system/system_ext/lib64/libjnisingleblur_api.qti.so").write_bytes(
        repair_front_blur_headers(front_jni.read_bytes()))
    camera_patches = {
        "donor_revision": revision,
        "source_files": {"system_ext/lib64/libjnisingleblur_api.so": FRONT_BLUR_SHA256},
        "files": {},
        "patches": ["Front portrait: Qualcomm JNI alias with mapped ELF program headers"],
    }
    front_path = "system/system_ext/lib64/libjnisingleblur_api.qti.so"
    camera_patches["files"][front_path] = hashlib.sha256((stage / front_path).read_bytes()).hexdigest()
    if film_guard:
        camera_patches["source_files"]["system_ext/priv-app/OplusCamera/OplusCamera.apk"] = APK_SHA256
        camera_patches["files"]["system/system_ext/priv-app/OplusCamera/OplusCamera.apk"] = hashlib.sha256(args.apk.read_bytes()).hexdigest()
        camera_patches["patches"].append("Film LOG and stabilization: mutually exclusive preferences with UI notifications and saved-state repair")
    if args.sdk:
        sdk_source = source / "system_ext/framework/com.oplus.camera.unit.sdk.jar"
        if hashlib.sha256(sdk_source.read_bytes()).hexdigest() != CAMERA_SDK_SHA256:
            raise SystemExit("Unexpected camera SDK source")
        with zipfile.ZipFile(args.sdk) as archive:
            if archive.testzip() or "classes.dex" not in archive.namelist():
                raise SystemExit("Patched camera SDK is damaged")
        shutil.copyfile(args.sdk, stage / "system/system_ext/framework/com.oplus.camera.unit.sdk.jar")
        camera_patches["source_files"]["system_ext/framework/com.oplus.camera.unit.sdk.jar"] = CAMERA_SDK_SHA256
        camera_patches["files"]["system/system_ext/framework/com.oplus.camera.unit.sdk.jar"] = hashlib.sha256(args.sdk.read_bytes()).hexdigest()
        camera_patches["patches"].append("Pro white balance: CamX manual temperature with AWB enabled; Auto clears override")
    (stage / "camera-patches.json").write_text(json.dumps(camera_patches, indent=2) + "\n")

    native_entries = []
    if args.native_cache:
        native_entries = json.loads((args.native_cache / "manifest.json").read_text())
        from native_access import EIS_LIBRARIES
        if any(entry["path"] in EIS_LIBRARIES for entry in native_entries) and not args.candidate_version:
            raise SystemExit("The unvalidated EIS library-access trial requires --candidate-version")
        labels = []
        for entry in native_entries:
            remote = pathlib.PurePosixPath(entry["path"])
            if remote.parts[:3] not in [("/", "odm", "lib64"), ("/", "vendor", "lib64")] or ".." in remote.parts:
                raise SystemExit(f"Invalid native path: {remote}")
            local = args.native_cache / str(remote).lstrip("/")
            if hashlib.sha256(local.read_bytes()).hexdigest() != entry["sha256"]:
                raise SystemExit(f"Native checksum mismatch: {remote}")
            relative = pathlib.Path("system/vendor/odm" if remote.parts[1] == "odm" else "system/vendor") / pathlib.Path(*remote.parts[2:])
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, target)
            labels.append(str(relative))
        (stage / "native-labels.txt").write_text("\n".join(labels) + "\n")
        # Publish only firmware provenance, not collection diagnostics or any
        # extra fields added to a local device manifest.
        public_entries = [{key: entry[key] for key in ("path", "label", "sha256", "size")}
                          for entry in native_entries]
        (stage / "native-source.json").write_text(json.dumps(public_entries, indent=2) + "\n")
    if args.filter_cache:
        args.filter_cache.mkdir(parents=True, exist_ok=True)
        filter_paths = []
        installed_filters = {}
        for name, digest in FILTER_LIBRARIES.items():
            local = args.filter_cache / name
            if not local.exists():
                url = (FILTER_REPOSITORY.replace("github.com", "raw.githubusercontent.com")
                       + f"/{FILTER_REVISION}/proprietary/odm/lib64/{name}")
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read()
                if hashlib.sha256(data).hexdigest() != digest:
                    raise SystemExit(f"Filter download checksum mismatch: {name}")
                local.write_bytes(data)
            if hashlib.sha256(local.read_bytes()).hexdigest() != digest:
                raise SystemExit(f"Filter library checksum mismatch: {name}")
            relative = pathlib.Path("system/vendor/odm/lib64") / name
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            patched = remove_alog_dependency(local.read_bytes())
            target.write_bytes(patched)
            installed_filters[name] = hashlib.sha256(patched).hexdigest()
            filter_paths.append(str(relative))
        with (stage / "native-labels.txt").open("a") as labels:
            labels.write("\n".join(filter_paths) + "\n")
        (stage / "filter-source.json").write_text(json.dumps({
            "repository": FILTER_REPOSITORY, "revision": FILTER_REVISION,
            "files": installed_filters, "source_files": FILTER_LIBRARIES,
            "patches": ["Remove unused libalog.so DT_NEEDED dependency"],
        }, indent=2) + "\n")
    if args.camera_config:
        json.loads(args.camera_config.read_text())
        target = stage / "system/vendor/odm/etc/camera/config/oplus_camera_config"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.camera_config, target)

    if args.blur_cache:
        if not args.native_cache:
            raise SystemExit("Blur packaging requires the verified firmware native cache")
        args.blur_cache.mkdir(parents=True, exist_ok=True)
        blur = {}
        for name, digest in BLUR_LIBRARIES.items():
            local = args.blur_cache / name
            if not local.exists():
                url = (BLUR_REPOSITORY.replace("github.com", "raw.githubusercontent.com")
                       + f"/{BLUR_REVISION}/proprietary/odm/lib64/{name}")
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read()
                if hashlib.sha256(data).hexdigest() != digest:
                    raise SystemExit(f"Blur download checksum mismatch: {name}")
                local.write_bytes(data)
            data = local.read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise SystemExit(f"Blur library checksum mismatch: {name}")
            blur[name] = data
        loader = (args.native_cache / "odm/lib64/libsnpe_loader.so").read_bytes()
        blur["libAncHumBokeh.so"], blur["liboosb_loader.so"] = patch_blur_libraries(
            blur["libAncHumBokeh.so"], loader)
        installed_blur = {}
        with (stage / "native-labels.txt").open("a") as labels:
            for name, data in blur.items():
                relative = pathlib.Path("system/vendor/odm/lib64") / name
                (stage / relative).write_bytes(data)
                labels.write(str(relative) + "\n")
                installed_blur[name] = hashlib.sha256(data).hexdigest()
        (stage / "blur-source.json").write_text(json.dumps({
            "repository": BLUR_REPOSITORY, "revision": BLUR_REVISION,
            "files": installed_blur, "source_files": BLUR_LIBRARIES,
            "firmware_loader": {"path": "/odm/lib64/libsnpe_loader.so",
                                "sha256": BLUR_LOADER_SHA256},
            "patches": ["Use a private liboosb_loader.so for video blur",
                        "Request GPU_FLOAT16 before the existing availability check"],
        }, indent=2) + "\n")

    if args.retouch_cache:
        data = (args.retouch_cache / "odm/lib64/lib2DSlender.so").read_bytes()
        if hashlib.sha256(data).hexdigest() != RETOUCH_SHA256:
            raise SystemExit("Retouch library checksum mismatch")
        relative = pathlib.Path("system/vendor/odm/lib64/lib2DSlender.so")
        (stage / relative).parent.mkdir(parents=True, exist_ok=True)
        (stage / relative).write_bytes(data)
        with (stage / "native-labels.txt").open("a") as labels:
            labels.write(str(relative) + "\n")
        (stage / "retouch-source.json").write_text(json.dumps({
            "repository": RETOUCH_REPOSITORY, "revision": RETOUCH_REVISION,
            "files": {"lib2DSlender.so": RETOUCH_SHA256},
            "source_files": {"lib2DSlender.so": RETOUCH_SHA256},
            "patches": [],
        }, indent=2) + "\n")

    if args.gralloc_cache:
        data = (args.gralloc_cache / "libgrallocutils.so").read_bytes()
        if hashlib.sha256(data).hexdigest() != GRALLOC_PATCHED_SHA256:
            raise SystemExit("Graphics candidate checksum mismatch")
        relative = pathlib.Path("system/vendor/lib64/libgrallocutils.so")
        (stage / relative).parent.mkdir(parents=True, exist_ok=True)
        (stage / relative).write_bytes(data)
        with (stage / "native-labels.txt").open("a") as labels:
            labels.write(str(relative) + "\n")
        (stage / "gralloc-source.json").write_text(json.dumps({
            "source_sha256": GRALLOC_SOURCE_SHA256,
            "patched_sha256": GRALLOC_PATCHED_SHA256,
            "previous_patched_sha256": GRALLOC_PREVIOUS_SHA256,
            "device_library": "/vendor/lib64/libgrallocutils.so",
            "scope": "Legacy 10-bit CAMERA_OUTPUT: PRIVATE selects codec-compatible linear VENUS P010",
            "status": "Unvalidated graphics trial; source match required",
        }, indent=2) + "\n")

    if args.gralloc32_cache:
        data = (args.gralloc32_cache / "libgrallocutils.so").read_bytes()
        if hashlib.sha256(data).hexdigest() != GRALLOC32_PATCHED_SHA256:
            raise SystemExit("ARMv7 graphics candidate checksum mismatch")
        relative = pathlib.Path("system/vendor/lib/libgrallocutils.so")
        (stage / relative).parent.mkdir(parents=True, exist_ok=True)
        (stage / relative).write_bytes(data)
        with (stage / "native-labels.txt").open("a") as labels:
            labels.write(str(relative) + "\n")
        (stage / "gralloc32-source.json").write_text(json.dumps({
            "source_sha256": GRALLOC32_SOURCE_SHA256,
            "patched_sha256": GRALLOC32_PATCHED_SHA256,
            "previous_patched_sha256": GRALLOC32_PREVIOUS_SHA256,
            "device_library": "/vendor/lib/libgrallocutils.so",
            "scope": "Legacy 10-bit CAMERA_OUTPUT: PRIVATE selects codec-compatible linear VENUS P010",
            "status": "Unvalidated ARMv7 graphics trial; matching ARM64 trial required",
        }, indent=2) + "\n")

    # After every other payload: anything the module already ships wins.
    if args.aox_cam4_cache:
        stage_aox_cam4(stage, args.aox_cam4_cache, args.uah_client)

    permissions = stage / "system/system_ext/etc/permissions"
    permissions.mkdir(parents=True, exist_ok=True)
    doc = ET.parse(donor / "configs/permissions/privapp-permissions-oplus.xml")
    for node in list(doc.getroot()):
        if node.tag == "privapp-permissions" and node.get("package") != "com.oplus.camera":
            doc.getroot().remove(node)
    # Expose the wrapper through an app library dependency, rather than adding
    # an unverified OEM JAR to the device's global boot classpath.
    ET.SubElement(doc.getroot(), "library", {
        "name": "org.ooscamera.compat", "file": "/system/framework/oplus-support-wrapper.jar"})
    for node in doc.getroot().findall("library"):
        if node.get("name", "").startswith("com.oplus.camera.unit.sdk"):
            node.set("dependency", "org.ooscamera.compat")
    ET.indent(doc)
    doc.write(permissions / "ooscamera-op9.xml", encoding="utf-8", xml_declaration=True)
    sysconfig = stage / "system/etc/sysconfig"
    sysconfig.mkdir(parents=True, exist_ok=True)
    (sysconfig / "ooscamera-hidden-api.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<config><hidden-api-whitelisted-app package="com.oplus.camera"/></config>\n')
    for name in ["module.prop", "customize.sh", "post-fs-data.sh", "action.sh",
                 "mount-camera.sh", "boot-completed.sh", "skip_mount"]:
        shutil.copyfile(ROOT / "module" / name, stage / name)
    if args.visibility_cache:
        from prepare_visibility import REVISION as VISIBILITY_REVISION
        visibility = json.loads((args.visibility_cache / "source.json").read_text())
        helper = (args.visibility_cache / "ksu-visibility").read_bytes()
        if (visibility.get("revision") != VISIBILITY_REVISION or visibility.get("profile_abi") != 3 or
                visibility.get("binary_sha256") != hashlib.sha256(helper).hexdigest() or
                visibility.get("source_sha256") != hashlib.sha256((ROOT / "native/ksu_visibility.c").read_bytes()).hexdigest()):
            raise SystemExit("Visibility helper source or payload mismatch")
        (stage / "ksu-visibility").write_bytes(helper)
        visibility["status"] = "Experimental automatic setup; candidate device checks pending"
        (stage / "visibility-source.json").write_text(json.dumps(visibility, indent=2) + "\n")
        for name in ("service.sh", "uninstall.sh", "visibility.sh"):
            shutil.copyfile(ROOT / "module" / name, stage / name)
    if args.candidate_version:
        prop = stage / "module.prop"
        text = re.sub(r"(?m)^version=.*$", "version=" + args.candidate_version, prop.read_text())
        text = re.sub(r"(?m)^name=(.*)$", r"name=\1 — TEST BUILD", text)
        text = re.sub(r"(?m)^description=.*$",
                      "description=Unvalidated compatibility candidate; device tests pending.", text)
        prop.write_text(text)
    final_apk = stage / "system/system_ext/priv-app/OplusCamera/OplusCamera.apk"
    manifest = {"donor_url": "https://github.com/dev-sm8350/vendor_oplus_camera",
                "donor_revision": revision, "camera_apk_sha256": APK_SHA256,
                "installed_apk_sha256": hashlib.sha256(final_apk.read_bytes()).hexdigest(),
                "status": "experimental; device validation required", "files": {}}
    for path in sorted(stage.rglob("*")):
        if path.is_file():
            manifest["files"][str(path.relative_to(stage))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (stage / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    properties = dict(line.split("=", 1) for line in (stage / "module.prop").read_text().splitlines()
                      if "=" in line and not line.startswith("#"))
    version = properties["version"]
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:-[A-Za-z0-9.-]+)?", version):
        raise SystemExit("Module version is not suitable for an artifact filename")
    output = output_dir / f"ooscamera-op9-{version}.zip"
    temporary = output.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                # Fixed ZIP epoch: do not publish the local build date or time.
                info = zipfile.ZipInfo(str(path.relative_to(stage)), (1980, 1, 1, 0, 0, 0))
                info.external_attr = (0o100755 if path.suffix == ".sh" else 0o100644) << 16
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    temporary.replace(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n")
    # Preserve the existing local install/audit entry point.
    latest = output_dir / "ooscamera-op9.zip"
    latest.unlink(missing_ok=True)
    latest.symlink_to(output.name)
    latest.with_suffix(".zip.sha256").write_text(f"{digest}  {latest.name}\n")
    print(f"{output}: {output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
