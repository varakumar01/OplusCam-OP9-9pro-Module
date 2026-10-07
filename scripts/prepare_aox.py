#!/usr/bin/env python3
"""Fetch everything build.py needs into the aox cache, verified by SHA-256.

Downloads every file listed in aox/manifest.json from the pinned revisions of
the aox trees, the build inputs, and the public AOSP platform test key the
camera APK is signed with. Configuration changes are not downloaded: they
are applied on the device as edits (module/aox/edits.txt). With --fixtures,
also fetch the base and head configuration files used by tests/test_aox.py.
"""
import argparse
import base64
import concurrent.futures
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
# Public AOSP test key (platform/build, target/product/security).
KEY_REVISION = "045a3d6a3e359633a14853a5a5e1e4f2a11cbdae"
KEY_FILES = {
    "platform.pk8": "1ad8ef556870edb70f69a9d3c112544c07de5162ba440d84d33f8bb0c5962875",
    "platform.x509.pem": "9837de028f460c35cc8d3fa45f14eecce30f6fbfe4b93d399aef1acb80c20d14",
}


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


def cache_path(cache, entry):
    """Per-device files live under their device name."""
    return cache / entry.get("device", "") / entry["path"]


def ensure(local, digest, urls, label):
    if local.exists() and hashlib.sha256(local.read_bytes()).hexdigest() == digest:
        return False
    data = b"".join(fetch(url) for url in urls)
    if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise SystemExit(f"Unresolved LFS pointer: {label}")
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f"Checksum mismatch: {label}")
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(data)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=pathlib.Path, default=ROOT / ".cache/aox")
    parser.add_argument("--fixtures", action="store_true",
                        help="Also fetch base/head configuration fixtures for host tests")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    sources = manifest["sources"]

    def source_url(name, path):
        return raw_url(sources[name]["repository"], sources[name]["revision"], path)

    jobs = []
    for entry in manifest["files"]:
        paths = entry.get("parts") or ["proprietary/" + entry["path"]]
        jobs.append((cache_path(args.cache, entry), entry["sha256"],
                     [source_url(entry["source"], path) for path in paths], entry["path"]))
    for entry in manifest["inputs"]:
        url = entry.get("url") or source_url(entry["source"], entry["src"])
        jobs.append((args.cache / "inputs" / entry["name"], entry["sha256"], [url], entry["name"]))
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        fetched = sum(pool.map(lambda job: ensure(*job), jobs))
    for name, digest in KEY_FILES.items():
        local = args.cache / "keys" / name
        if not local.exists() or hashlib.sha256(local.read_bytes()).hexdigest() != digest:
            data = base64.b64decode(fetch(
                "https://android.googlesource.com/platform/build/+/"
                f"{KEY_REVISION}/target/product/security/{name}?format=TEXT"))
            if hashlib.sha256(data).hexdigest() != digest:
                raise SystemExit(f"Checksum mismatch: {name}")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
    (args.cache / "source.json").write_text(json.dumps({"sources": sources}, indent=2) + "\n")
    if args.fixtures:
        fixtures = args.cache / "fixtures"
        for device in ("lemonade", "lemonadep"):
            pin = manifest["fixtures"][device]
            repository = sources[pin["source"]]["repository"]
            for name, revision in (("base", pin["base"]), ("head", sources[pin["source"]]["revision"])):
                for path in CONFIGS:
                    target = fixtures / device / name / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(fetch(raw_url(repository, revision, "proprietary/" + path)))
        pin = manifest["fixtures"]["media"]
        repository = sources[pin["source"]]["repository"]
        for name, revision in (("base", pin["base"]), ("head", sources[pin["source"]]["revision"])):
            target = fixtures / "lemonade" / name / "vendor/etc/media_profiles_vendor.xml"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(fetch(raw_url(repository, revision, MEDIA)))
        print(f"fixtures in {fixtures}")
    print(f"{len(jobs)} aox files verified in {args.cache} ({fetched} fetched)")


if __name__ == "__main__":
    main()
