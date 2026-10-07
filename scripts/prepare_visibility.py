#!/usr/bin/env python3
"""Compile an experimental profile helper, without adding it to any module."""
import argparse
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
REVISION = "551ad80473f60e052917aec08abf5323b6ab2f7c"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path,
                        default=ROOT / ".cache/donor/ksu-next/source")
    parser.add_argument("--ndk", type=pathlib.Path,
                        default=pathlib.Path.home() / "Android/Sdk/ndk/27.2.12479018")
    parser.add_argument("--output-dir", type=pathlib.Path,
                        default=ROOT / "build/visibility-candidate")
    parser.add_argument("--device-test-harness", action="store_true",
                        help="Also compile the developer-only reversible policy fixture")
    args = parser.parse_args()
    source = args.source.resolve()
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise SystemExit("Unexpected KernelSU UAPI revision")
    headers = {}
    for name in ("uapi/app_profile.h", "uapi/supercall.h"):
        data = (source / name).read_bytes()
        original = subprocess.check_output(["git", "-C", str(source), "show", f"{REVISION}:{name}"])
        if data != original:
            raise SystemExit("Modified KernelSU UAPI header")
        headers[name] = hashlib.sha256(data).hexdigest()
    toolchain = args.ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / "ksu-visibility"
    subprocess.run([str(toolchain / "aarch64-linux-android30-clang"), "-O2",
                    "-Wall", "-Wextra", "-Werror", "-Wl,--build-id=none",
                    f"-ffile-prefix-map={ROOT}=/src", "-I", str(source),
                    str(ROOT / "native/ksu_visibility.c"), "-o", str(target)], check=True)
    subprocess.run([str(toolchain / "llvm-strip"), "--strip-all", str(target)], check=True)
    manifest = {
        "status": "Experimental; not installed or packaged; device validation required",
        "repository": "https://github.com/KernelSU-Next/KernelSU-Next",
        "revision": revision, "profile_abi": 3, "headers": headers,
        "source_sha256": hashlib.sha256((ROOT / "native/ksu_visibility.c").read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "notes": ["Root delegates the manager's real UID only for profile ioctls",
                  "Only Camera/current owner-user launcher and unshared app UIDs may be configured",
                  "Root grants and global defaults are preserved",
                  "Original policies backed up before mutation; later user edits preserved on restore"],
    }
    (output / "source.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.device_test_harness:
        subprocess.run([str(toolchain / "aarch64-linux-android30-clang"), "-O2",
                        "-Wall", "-Wextra", "-Werror", f"-ffile-prefix-map={ROOT}=/src",
                        "-I", str(source), str(ROOT / "tests/visibility_policy_device.c"),
                        "-o", str(output / "visibility-policy-test")], check=True)
    print(target)


if __name__ == "__main__":
    main()
