#!/usr/bin/env python3
"""Patch the pinned, app-scoped camera SDK; never edit a boot framework JAR."""
import argparse
import hashlib
import pathlib
import re
import subprocess

from patch_apk import normalize_apk_metadata

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDK_SHA256 = "4ee8f097d63d9766bafba1bf9a3073363443ad5fa007f2f9ce83005cb3c461b5"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apktool", type=pathlib.Path, default=ROOT / ".cache/tools/apktool.jar")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "build")
    ratios = parser.add_mutually_exclusive_group()
    ratios.add_argument("--experimental-photo-ratio", action="store_true",
                        help="Include the unvalidated square Photo reprocessing candidate")
    ratios.add_argument("--experimental-all-photo-ratios", action="store_true",
                        help="Prepare advertised rear-camera YUV sizing for non-4:3 Photo; needs device tests")
    args = parser.parse_args()
    source = ROOT / ".cache/donor/op9/proprietary/system_ext/framework/com.oplus.camera.unit.sdk.jar"
    if hashlib.sha256(source.read_bytes()).hexdigest() != SDK_SHA256:
        raise SystemExit("Unexpected camera SDK source")
    work = ROOT / ".cache/sdk-work"
    subprocess.run(["java", "-jar", str(args.apktool), "d", "-f", str(source), "-o", str(work)], check=True)
    mode = work / "smali/com/oplus/ocs/camera/producer/mode/ProfessionalMode.smali"
    replacement = (ROOT / "patches/pro-white-balance.smali").read_text().rstrip()
    text, count = re.subn(
        r"(?ms)^\.method private checkColorTemperature\(Lcom/oplus/ocs/camera/metadata/parameter/PreviewParameter\$Builder;\)V\n.*?^\.end method$",
        lambda match: replacement, mode.read_text())
    if count != 1:
        raise SystemExit("Expected exactly one Pro white-balance request method")
    mode.write_text(text)
    if args.experimental_photo_ratio or args.experimental_all_photo_ratios:
        photo = work / "smali/com/oplus/ocs/camera/producer/mode/PhotoMode.smali"
        signature = (".method public getSurfaceSize("
                     "Lcom/oplus/ocs/camera/common/parameter/SdkCameraDeviceConfig;"
                     "Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;I)Ljava/util/List;")
        original = photo.read_text()
        if original.count(signature) != 1:
            raise SystemExit("Expected exactly one Photo surface-size method")
        original = original.replace(signature, signature.replace("getSurfaceSize(",
                                                                 "getOriginalSurfaceSize("), 1)
        fragment = ("photo-ratio-reprocess.smali" if args.experimental_all_photo_ratios
                    else "photo-square-reprocess.smali")
        wrapper = (ROOT / "patches" / fragment).read_text()
        photo.write_text(original + "\n" + wrapper)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "camera-sdk-unnormalized.jar"
    subprocess.run(["java", "-jar", str(args.apktool), "b", str(work), "-o", str(temporary)], check=True)
    target = output / "com.oplus.camera.unit.sdk.jar"
    normalize_apk_metadata(temporary, target)
    print(target)


if __name__ == "__main__":
    main()
