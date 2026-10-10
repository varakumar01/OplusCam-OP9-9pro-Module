#!/usr/bin/env python3
"""Compile the app profile helper (native/ksu_visibility.c) for arm64 Android."""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "native/ksu_visibility.c"
PROFILE_VERSIONS = [3, 4]


def default_ndk():
    for name in ("ANDROID_NDK_LATEST_HOME", "ANDROID_NDK_HOME", "ANDROID_NDK"):
        if os.environ.get(name):
            return pathlib.Path(os.environ[name])
    return pathlib.Path.home() / "Android/Sdk/ndk/27.2.12479018"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=pathlib.Path, default=default_ndk())
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "build/visibility")
    parser.add_argument("--device-test-harness", action="store_true",
                        help="Also compile the developer-only reversible policy fixture")
    args = parser.parse_args()
    toolchain = args.ndk / "toolchains/llvm/prebuilt/linux-x86_64/bin"
    compiler = toolchain / "aarch64-linux-android30-clang"
    if not compiler.exists():
        raise SystemExit(f"No Android NDK at {args.ndk} (pass --ndk)")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / "ksu-visibility"
    flags = ["-O2", "-Wall", "-Wextra", "-Werror", f"-ffile-prefix-map={ROOT}=/src"]
    subprocess.run([str(compiler), *flags, "-Wl,--build-id=none", str(SOURCE), "-o", str(target)], check=True)
    subprocess.run([str(toolchain / "llvm-strip"), "--strip-all", str(target)], check=True)
    manifest = {
        "profile_versions": PROFILE_VERSIONS,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "binary_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "notes": ["Root delegates the manager's real UID only for profile ioctls",
                  "Only Camera/current owner-user launcher and unshared app UIDs may be configured",
                  "Root grants and global defaults are preserved",
                  "Original policies backed up before mutation; later user edits preserved on restore"],
    }
    (output / "source.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if args.device_test_harness:
        subprocess.run([str(compiler), *flags, str(ROOT / "tests/visibility_policy_device.c"),
                        "-o", str(output / "visibility-policy-test")], check=True)
    print(target)


if __name__ == "__main__":
    main()
