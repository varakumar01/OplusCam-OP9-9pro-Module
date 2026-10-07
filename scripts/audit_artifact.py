#!/usr/bin/env python3
"""Audit a shareable module without printing the identifiers being searched."""
import argparse
import hashlib
import io
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
EPOCH = (1980, 1, 1, 0, 0, 0)
CAMERA_APK = "system/system_ext/priv-app/OplusCamera/OplusCamera.apk"
CONTROL_FILES = {
    "module.prop", "customize.sh", "post-fs-data.sh", "action.sh",
    "mount-camera.sh", "boot-completed.sh", "skip_mount",
    "service.sh", "uninstall.sh", "visibility.sh", "ksu-visibility", "visibility-source.json",
    "native-labels.txt", "native-source.json", "provenance.json", "filter-source.json",
    "blur-source.json", "retouch-source.json", "gralloc-source.json", "gralloc32-source.json", "camera-patches.json",
    "aox-cam4.sh", "sepolicy.rule", "aox-cam4-source.json",
    "aox-cam4/edits.txt", "aox-cam4/files.txt",
}
PRIVATE_KEY = re.compile(
    rb"-----BEGIN (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----\s+"
    rb"[A-Za-z0-9+/=\r\n]{64,}-----END (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----"
)


def allowed_payload(name):
    if name in CONTROL_FILES:
        return True
    if name == CAMERA_APK:
        return True
    if name.startswith(("system/system_ext/lib64/", "system/vendor/lib64/", "system/vendor/lib/",
                        "system/vendor/odm/lib64/")) and name.endswith(".so"):
        return True
    if name.startswith("aox-cam4/blocks/") and name.endswith((".old", ".new")):
        return True
    if name.startswith("system/vendor/odm/lib/rfsa/adsp/") and name.endswith(".so"):
        return True
    if name.startswith(("system/framework/", "system/system_ext/framework/")) and name.endswith(".jar"):
        return True
    if name.startswith(("system/etc/sysconfig/", "system/system_ext/etc/permissions/",
                        "system/system_ext/etc/default-permissions/")) and name.endswith(".xml"):
        return True
    return name in {
        "system/vendor/odm/etc/camera/config/oplus_camera_config",
        "system/vendor/odm/etc/camera/config/camera_unit_feature_config.protobuf",
        "system/vendor/odm/etc/camera/license_release_fdc.lic",
        "system/vendor/odm/etc/camera/model/license.lic",
        "system/vendor/odm/etc/camera/singleblur/license_release.lic",
        "system/vendor/odm/etc/camera/singleblur/license_release.license",
    }


def audit(archive_path, identifiers):
    errors = []
    files_scanned = 0
    needles = [(index, value.encode(encoding)) for index, value in enumerate(identifiers)
               for encoding in ("utf-8", "utf-16le", "utf-16be")]

    def scan(name, data):
        nonlocal files_scanned
        files_scanned += 1
        for index, needle in needles:
            if needle in data:
                errors.append(f"Known identifier #{index + 1} in {name}")
        if PRIVATE_KEY.search(data):
            errors.append(f"Private key block in {name}")

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            errors.append("Duplicate module entries")
        if archive.comment:
            errors.append("Module ZIP comment is not empty")
        for entry in archive.infolist():
            if not allowed_payload(entry.filename) or ".." in pathlib.PurePosixPath(entry.filename).parts:
                errors.append(f"Unexpected payload: {entry.filename}")
            if entry.date_time != EPOCH or entry.extra or entry.comment:
                errors.append(f"Non-normalized module metadata: {entry.filename}")
            data = archive.read(entry)
            scan(entry.filename, data)
            scan(entry.filename + " [metadata]", entry.filename.encode() + entry.extra + entry.comment)
            if entry.filename.endswith((".apk", ".jar")):
                with zipfile.ZipFile(io.BytesIO(data)) as nested:
                    if nested.comment:
                        errors.append(f"Nested archive comment in {entry.filename}")
                    for member in nested.infolist():
                        location = entry.filename + "!/" + member.filename
                        scan(location, nested.read(member))
                        scan(location + " [metadata]", member.filename.encode() + member.extra + member.comment)
                        if entry.filename == CAMERA_APK and member.date_time != EPOCH:
                            errors.append(f"Non-normalized APK timestamp: {member.filename}")

        provenance = json.loads(archive.read("provenance.json"))
        expected = {"donor_url", "donor_revision", "camera_apk_sha256",
                    "installed_apk_sha256", "status", "files"}
        if set(provenance) != expected:
            errors.append("Unexpected provenance fields")
        if set(provenance["files"]) != set(names) - {"provenance.json"}:
            errors.append("Incomplete payload checksum manifest")
        for name, digest in provenance["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                errors.append(f"Checksum mismatch: {name}")
        if hashlib.sha256(archive.read(CAMERA_APK)).hexdigest() != provenance["installed_apk_sha256"]:
            errors.append("Camera APK checksum mismatch")
        if "camera-patches.json" in names:
            patches = json.loads(archive.read("camera-patches.json"))
            if set(patches) != {"donor_revision", "source_files", "files", "patches"}:
                errors.append("Unexpected camera patch provenance fields")
            if patches["donor_revision"] != provenance["donor_revision"]:
                errors.append("Camera patch donor revision mismatch")
            for name, digest in patches["files"].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                    errors.append(f"Camera patch checksum mismatch: {name}")
        # Builds without --native-cache (no device collection) have no manifest.
        native = json.loads(archive.read("native-source.json")) if "native-source.json" in names else []
        for entry in native:
            if set(entry) != {"path", "label", "sha256", "size"}:
                errors.append("Native manifest contains collection or unknown fields")
        if "visibility-source.json" in names:
            from prepare_visibility import REVISION
            source = json.loads(archive.read("visibility-source.json"))
            if set(source) != {"status", "repository", "revision", "profile_abi", "headers", "source_sha256", "binary_sha256", "notes"}:
                errors.append("Unexpected visibility provenance fields")
            if (source.get("revision") != REVISION or source.get("profile_abi") != 3 or
                    source.get("repository") != "https://github.com/KernelSU-Next/KernelSU-Next"):
                errors.append("Visibility UAPI revision mismatch")
            if "ksu-visibility" not in names or hashlib.sha256(archive.read("ksu-visibility")).hexdigest() != source.get("binary_sha256"):
                errors.append("Visibility helper checksum mismatch")
            if not {"service.sh", "visibility.sh", "uninstall.sh"}.issubset(names):
                errors.append("Visibility lifecycle scripts missing")
        elif "ksu-visibility" in names:
            errors.append("Visibility helper lacks provenance")
        for manifest, abi in (("gralloc-source.json", "lib64"), ("gralloc32-source.json", "lib")):
            if manifest not in names:
                continue
            source = json.loads(archive.read(manifest))
            if set(source) not in ({"source_sha256", "patched_sha256", "device_library", "scope", "status"},
                                   {"source_sha256", "patched_sha256", "previous_patched_sha256", "device_library", "scope", "status"}):
                errors.append("Unexpected graphics provenance fields")
            payload = f"system/vendor/{abi}/libgrallocutils.so"
            if source.get("device_library") != f"/vendor/{abi}/libgrallocutils.so":
                errors.append("Graphics candidate ABI/path mismatch")
            if abi == "lib" and "gralloc-source.json" not in names:
                errors.append("ARMv7 graphics candidate lacks ARM64 counterpart")
            if hashlib.sha256(archive.read(payload)).hexdigest() != source.get("patched_sha256"):
                errors.append("Graphics candidate checksum mismatch")
        for filename in ("filter-source.json", "blur-source.json", "retouch-source.json"):
            if filename not in names:
                continue
            source = json.loads(archive.read(filename))
            schemas = ({"repository", "revision", "files"},
                       {"repository", "revision", "files", "source_files", "patches"})
            if filename == "blur-source.json":
                schemas = ({"repository", "revision", "files", "source_files", "patches", "firmware_loader"},)
                if set(source.get("firmware_loader", {})) != {"path", "sha256"}:
                    errors.append("Unexpected blur firmware provenance fields")
            if set(source) not in schemas:
                errors.append(f"Unexpected provenance fields in {filename}")
            for name, digest in source["files"].items():
                path = "system/vendor/odm/lib64/" + name
                if hashlib.sha256(archive.read(path)).hexdigest() != digest:
                    errors.append(f"OEM source checksum mismatch: {name}")
        if "aox-cam4-source.json" in names:
            source = json.loads(archive.read("aox-cam4-source.json"))
            for path, digest in source.get("files", {}).items():
                parts = pathlib.PurePosixPath(path).parts
                payload = ("system/vendor/" if parts[0] == "odm" else "system/") + path
                if payload not in names or hashlib.sha256(archive.read(payload)).hexdigest() != digest:
                    errors.append(f"aox-cam4 checksum mismatch: {path}")

    return {"passed": not errors, "module_entries": len(names),
            "files_and_metadata_scanned": files_scanned,
            "known_identifiers_checked": len(identifiers), "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", nargs="?", type=pathlib.Path,
                        default=ROOT / "build/ooscamera-op9.zip")
    parser.add_argument("--identifiers-file", type=pathlib.Path,
                        help="Private UTF-8 file with one known identifier per line")
    parser.add_argument("--report", type=pathlib.Path)
    args = parser.parse_args()
    identifiers = []
    if args.identifiers_file:
        identifiers = [line.strip() for line in args.identifiers_file.read_text().splitlines()
                       if line.strip()]
    result = audit(args.archive, identifiers)
    output = json.dumps(result, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end="")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
