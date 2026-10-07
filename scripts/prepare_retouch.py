#!/usr/bin/env python3
"""Prepare a pinned native Retouch trial without changing the release module."""
import argparse
import hashlib
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOSITORY = "https://github.com/resist15/vendor_realme_porsche"
REVISION = "8bdc52979f0fe9f424a92b62b7bf0c72e52b4c76"
SOURCE_PATH = "proprietary/odm/lib64/lib2DSlender.so"
SOURCE_SHA256 = "8219b2475c9cce095f550d99b30f3ec767be339ca1c3f0038096a131dd55bc02"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=pathlib.Path,
                        default=ROOT / ".cache/donor/retouch/porsche-lib2DSlender.so")
    parser.add_argument("--output-dir", type=pathlib.Path,
                        default=ROOT / "build/retouch-native-candidate")
    args = parser.parse_args()
    if args.cache.exists():
        data = args.cache.read_bytes()
    else:
        url = REPOSITORY.replace("github.com", "raw.githubusercontent.com")
        with urllib.request.urlopen(f"{url}/{REVISION}/{SOURCE_PATH}", timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise SystemExit("Retouch library source checksum mismatch")
    args.cache.parent.mkdir(parents=True, exist_ok=True)
    args.cache.write_bytes(data)
    output = args.output_dir.resolve()
    target = output / "odm/lib64/lib2DSlender.so"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(0o644)
    manifest = {
        "status": "Unvalidated native trial; not part of the release module",
        "repository": REPOSITORY,
        "revision": REVISION,
        "source_path": SOURCE_PATH,
        "sha256": SOURCE_SHA256,
        "target": "/odm/lib64/lib2DSlender.so",
        "target_selinux_label": "u:object_r:same_process_hal_file:s0",
        "notes": ["Slender2D entry points are present",
                  "No DT_NEEDED dependency or imported API symbols for SNPE",
                  "Calling ABI, initialization and visual effect need device tests"],
    }
    (output / "source.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
