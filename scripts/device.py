#!/usr/bin/env python3
"""ADB commands with explicit device selection and correctly quoted root commands."""
import argparse
import pathlib
import shlex
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def adb(*args, check=True, timeout=60):
    return subprocess.run(["adb", *args], text=True, errors="replace", capture_output=True,
                          check=check, timeout=timeout)


def root(command, check=True, timeout=60):
    return adb("shell", "su", "-c", shlex.quote(command), check=check, timeout=timeout)


def collect():
    out = ROOT / ".cache" / "device" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    commands = {
        "build": "getprop ro.crdroid.build.version; getprop ro.crdroid.display.version; "
                 "getprop ro.build.version.sdk; getprop ro.build.version.security_patch; "
                 "getprop ro.product.vendor.device; /data/adb/ksud -V; getenforce",
        "camera": "dumpsys media.camera",
        "package": "dumpsys package com.oplus.camera",
        "mounts": "cat /proc/mounts",
        "process": "ps -AZ | grep -E 'oplus.camera|cameraserver|camera.provider'",
        "module": "cat /data/adb/modules/ooscamera_op9/module.prop; "
                  "ls -l /data/adb/modules/ooscamera_op9/disable",
    }
    for name, command in commands.items():
        result = root(command, check=False)
        (out / f"{name}.txt").write_text(result.stdout + result.stderr)
    result = adb("logcat", "-d", "-t", "6000", "-v", "threadtime")
    (out / "logcat.txt").write_text(result.stdout)
    print(out)


def collect_native():
    """Read-only diagnostics for the beauty engine; leave all data private."""
    out = ROOT / ".cache" / "device" / time.strftime("native-%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    commands = {
        "beauty-files": "ls -lZ /odm/etc/camera/fb_default "
                        "/odm/etc/camera/config/pfb_param.txt "
                        "/odm/lib64/lib2DSlender.so /odm/lib64/libFaceBeautyJni.so "
                        "/odm/lib64/libFaceBeautyPre.so "
                        "/system_ext/lib64/libApsFaceBeautyPreviewProductJni.so "
                        "/system_ext/lib64/libApsFaceBeautyPreviewJni.qti.so",
        "beauty-config": "cat /odm/etc/camera/fb_default",
        "beauty-debug-config": "cat /odm/etc/camera/config/pfb_param.txt",
        "package-path": "pm path com.oplus.camera; dumpsys package com.oplus.camera",
        "native-maps": "pid=$(pidof com.oplus.camera); "
                       "[ -n \"$pid\" ] && cat /proc/$pid/maps",
        "mounts": "cat /proc/mounts",
        "thermal": "dumpsys thermalservice; dumpsys battery",
    }
    for name, command in commands.items():
        result = root(command, check=False)
        (out / f"{name}.txt").write_text(result.stdout + result.stderr)
    result = adb("logcat", "-d", "-t", "3000", "-v", "threadtime",
                 "PREVIEW_FB:V", "OplusFaceBeautyPreview:V", "libvndksupport:V",
                 "linker:V", "AndroidRuntime:E", "*:S")
    (out / "native-logcat.txt").write_text(result.stdout)
    result = adb("logcat", "-b", "crash", "-d", "-t", "200", "-v", "threadtime")
    (out / "crash.txt").write_text(result.stdout)
    print(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["collect", "collect-native", "install", "launch", "disable", "root"])
    parser.add_argument("argument", nargs="?")
    args = parser.parse_args()
    if args.command == "collect":
        collect()
    elif args.command == "collect-native":
        collect_native()
    elif args.command == "root":
        result = root(args.argument, check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise SystemExit(result.returncode)
    elif args.command == "install":
        archive = pathlib.Path(args.argument or ROOT / "build" / "ooscamera-op9.zip").resolve()
        if not archive.is_file():
            parser.error(f"Module archive missing: {archive}")
        adb("push", str(archive), "/data/local/tmp/ooscamera-op9.zip")
        result = root("/data/adb/ksud module install /data/local/tmp/ooscamera-op9.zip",
                      check=False, timeout=240)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise SystemExit(result.returncode)
    elif args.command == "disable":
        print(root("/data/adb/ksud module disable ooscamera_op9").stdout)
        print("Disabled for the next boot. Reboot to restore the previous system files.")
    elif args.command == "launch":
        result = adb("shell", "am", "start", "-W", "-n",
                     "com.oplus.camera/com.oplus.camera.Camera", check=False)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
