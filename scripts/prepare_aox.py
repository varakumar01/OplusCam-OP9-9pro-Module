#!/usr/bin/env python3
"""Fetch the pinned aox camera libraries for build.py --aox-cache.

Downloads every file listed in aox/manifest.json from the pinned
proprietary_vendor_oneplus_lemonade revision and verifies its SHA-256.
Configuration changes are not downloaded: they are applied on the device as
edits (module/aox/edits.txt). With --fixtures, also fetch the base and
head configuration files used by tests/test_aox.py.
"""
import argparse
import hashlib
import http.client
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "aox/manifest.json"
CONFIGS = [
    "odm/etc/camera/CameraHWConfiguration.config",
    "odm/etc/camera/config/camera_unit_config",
    "odm/etc/camera/config/oplus_camera_algo_switch_config",
    "odm/etc/camera/config/oplus_camera_aps_config",
    "odm/etc/camera/config/oplus_camera_config",
]
MEDIA = "media/media_profiles_vendor.xml"


def raw_url(repository, revision, path):
    return repository.replace("github.com", "raw.githubusercontent.com") + f"/{revision}/{path}"


def fetch(url, attempts=5):
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                return response.read()
        except (OSError, http.client.HTTPException) as error:
            if attempt == attempts:
                raise SystemExit(f"Download failed: {url}: {error}")
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=pathlib.Path, default=ROOT / ".cache/aox")
    parser.add_argument("--fixtures", action="store_true",
                        help="Also fetch base/head configuration fixtures for host tests")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    for entry in manifest["files"]:
        local = args.cache / entry["path"]
        if local.exists() and hashlib.sha256(local.read_bytes()).hexdigest() == entry["sha256"]:
            continue
        data = fetch(raw_url(manifest["repository"], manifest["revision"],
                             "proprietary/" + entry["path"]))
        if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
            raise SystemExit(f"Unresolved LFS pointer: {entry['path']}")
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise SystemExit(f"aox checksum mismatch: {entry['path']}")
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        print(f"fetched {entry['path']}")
    (args.cache / "source.json").write_text(json.dumps({
        "repository": manifest["repository"], "branch": manifest["branch"],
        "revision": manifest["revision"], "base_revision": manifest["base_revision"],
        "files": {entry["path"]: entry["sha256"] for entry in manifest["files"]},
    }, indent=2) + "\n")
    if args.fixtures:
        fixtures = args.cache / "fixtures"
        for name, revision in (("base", manifest["base_revision"]), ("head", manifest["revision"])):
            for path in CONFIGS:
                target = fixtures / name / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(fetch(raw_url(manifest["repository"], revision, "proprietary/" + path)))
        for name, revision in (("base", manifest["device_media_base_revision"]),
                               ("head", manifest["device_media_revision"])):
            target = fixtures / name / "vendor/etc/media_profiles_vendor.xml"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(fetch(raw_url(manifest["device_repository"], revision, MEDIA)))
        print(f"fixtures in {fixtures}")
    print(f"{len(manifest['files'])} aox files verified in {args.cache}")


if __name__ == "__main__":
    main()
