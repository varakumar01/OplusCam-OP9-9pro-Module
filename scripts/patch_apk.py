#!/usr/bin/env python3
"""Apply camera-only compatibility edits and sign with a stable local test key."""
import argparse
import os
import pathlib
import re
import subprocess
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def patch_retouch_process(text, enabled=True):
    """Reject failed beauty frames so the existing renderer uses its input."""
    call = ("    invoke-virtual {v6, v1, v7, v8, v4}, "
            "Lcom/oplus/ocs/camera/OplusFaceBeautyPreviewHelper;->process(I[I[I[I)I")
    guard = (call + "\n\n"
             "    # Preserve the input preview when native Retouch fails.\n"
             "    move-result v6\n"
             "    if-gez v6, :ooscamera_retouch_frame_ready\n"
             "    const/4 v5, 0x0\n"
             "    return v5\n"
             "    :ooscamera_retouch_frame_ready")
    if text.count(call) != 1:
        raise ValueError("Expected exactly one Retouch frame-processing call")
    if ":ooscamera_retouch_frame_ready" in text:
        if guard not in text or text.count(":ooscamera_retouch_frame_ready") != 2:
            raise ValueError("Unexpected existing Retouch guard")
        return text if enabled else text.replace(guard, call, 1)
    return text.replace(call, guard, 1) if enabled else text


def patch_retouch_logging(text, enabled=False):
    """Enable native initialization logs only in an explicit diagnostic APK."""
    original = "    :cond_6\n    move v11, v5"
    diagnostic = ("    :cond_6\n"
                  "    # Diagnostic build: verbose native beauty initialization.\n"
                  "    const/4 v11, 0x4")
    if diagnostic in text:
        if text.count(diagnostic) != 1 or original in text:
            raise ValueError("Unexpected Retouch diagnostic logging branch")
        return text if enabled else text.replace(diagnostic, original, 1)
    if text.count(original) != 1:
        raise ValueError("Expected exactly one Retouch initialization log-level branch")
    return text.replace(original, diagnostic, 1) if enabled else text


def patch_film_options(work, enabled=False):
    """Make Film LOG and EIS mutually exclusive in the explicit graphics trial."""
    manager = work / "smali/com/oplus/camera/data/DataManager.smali"
    presenter = next(work.glob("smali*/l8/j.smali"))
    notice = manager.with_name("OosCameraFilmNotice.smali")
    methods = "\n\n" + (ROOT / "patches/film-log-options.smali").read_text().rstrip() + "\n"
    setter_guard = ("    invoke-direct {p0, p1, p2}, "
                    "Lcom/oplus/camera/data/DataManager;"
                    "->ooscameraGuardFilmOptions(Lp6/a;Ljava/lang/Object;)V\n")
    entry_guard = ("    invoke-virtual {v0}, Lcom/oplus/camera/data/DataManager;"
                   "->ooscameraRestoreFilmOptions()V\n")
    text = manager.read_text()
    # Remove only our exact edits first, so repeated builds and opt-out are safe.
    if "ooscameraGuardFilmOptions" in text:
        if text.count(methods) != 1 or text.count(setter_guard) != 2:
            raise ValueError("Unexpected existing Film option guard")
        text = text.replace(methods, "", 1).replace(setter_guard, "")
    if enabled:
        for signature in ("f(Lp6/a;Ljava/lang/Object;)V", "g(Lp6/a;Ljava/lang/Object;Z)V"):
            header = f".method public final {signature}\n    .locals 1\n"
            if text.count(header) != 1:
                raise ValueError(f"Unexpected DataManager setter: {signature}")
            # Insert after the generic-signature annotation, before instructions.
            start = text.index(header)
            position = text.index("    .end annotation\n", start) + len("    .end annotation\n")
            text = text[:position] + setter_guard + text[position:]
        text += methods
    manager.write_text(text)
    text = presenter.read_text()
    if "ooscameraRestoreFilmOptions" in text:
        if text.count(entry_guard) != 1:
            raise ValueError("Unexpected existing Film entry guard")
        text = text.replace(entry_guard, "", 1)
    anchor = "    move-result-object v0\n\n    .line 29\n    sget-object v3, Lr6/g;->k:Lp6/a;"
    if text.count(anchor) != 1:
        raise ValueError("Expected exactly one Film stabilization initialization")
    if enabled:
        text = text.replace(anchor, anchor.replace("\n\n    .line 29", "\n" + entry_guard + "\n    .line 29"), 1)
        notice.write_text((ROOT / "patches/film-log-notice.smali").read_text())
    else:
        notice.unlink(missing_ok=True)
    presenter.write_text(text)
    patch_film_ui(work, enabled)


def patch_film_ui(work, enabled=False):
    """Synchronize the actual toolbar model after its click handlers mutate it."""
    base = next(work.glob("smali*/yh/c.smali"))
    methods = "\n\n" + (ROOT / "patches/film-log-ui.smali").read_text().rstrip() + "\n"
    init = ("    invoke-static {}, Lcom/oplus/camera/data/DataManager;->getInstance()Lcom/oplus/camera/data/DataManager;\n"
            "    move-result-object v1\n"
            "    invoke-virtual {v1}, Lcom/oplus/camera/data/DataManager;->ooscameraRestoreFilmOptions()V\n")
    text = base.read_text()
    if "ooscameraRefreshFilmOptions" in text:
        if text.count(methods) != 1 or text.count(init) != 1:
            raise ValueError("Unexpected existing Film UI initialization guard")
        text = text.replace(methods, "", 1).replace(init, "", 1)
    anchor = ".method public final t8(ZZZ)V\n    .locals 16\n"
    if text.count(anchor) != 1:
        raise ValueError("Expected exactly one Film toolbar initialization")
    if enabled:
        text = text.replace(anchor, anchor + init, 1) + methods
    base.write_text(text)
    for name, modifiers in (("t", "public"), ("f", "public final"), ("l", "public final")):
        path = next(work.glob(f"smali*/yh/{name}.smali"))
        original = f".method {modifiers} R0(Landroid/view/View;I)V\n"
        renamed = ".method private ooscameraFilmClickOriginal(Landroid/view/View;I)V\n"
        wrapper = ("\n\n" + original + "    .locals 0\n"
                   f"    invoke-direct {{p0, p1, p2}}, Lyh/{name};->ooscameraFilmClickOriginal(Landroid/view/View;I)V\n"
                   "    invoke-virtual {p0}, Lyh/c;->ooscameraRefreshFilmOptions()V\n"
                   "    return-void\n.end method\n")
        text = path.read_text()
        if "ooscameraFilmClickOriginal" in text:
            if text.count(wrapper) != 1 or text.count(renamed) != 1:
                raise ValueError(f"Unexpected existing Film UI click wrapper: {name}")
            text = text.replace(wrapper, "", 1).replace(renamed, original, 1)
        if text.count(original) != 1:
            raise ValueError(f"Expected exactly one Film click handler: {name}")
        if enabled:
            text = text.replace(original, renamed, 1) + wrapper
        path.write_text(text)


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def normalize_apk_metadata(source, target):
    """Remove build timestamps and ZIP extras before alignment and signing."""
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(target, "w") as output:
        for entry in original.infolist():
            # Signature files are regenerated by apksigner below.
            name = entry.filename.upper()
            if name == "META-INF/MANIFEST.MF" or (
                name.startswith("META-INF/") and name.endswith((".SF", ".RSA", ".DSA", ".EC"))
            ):
                continue
            info = zipfile.ZipInfo(entry.filename, (1980, 1, 1, 0, 0, 0))
            info.compress_type = entry.compress_type
            info.external_attr = (0o100644 if not entry.is_dir() else 0o40755) << 16
            output.writestr(info, original.read(entry))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apktool", type=pathlib.Path, default=ROOT / ".cache/tools/apktool.jar")
    parser.add_argument("--output-dir", type=pathlib.Path, default=ROOT / "build")
    parser.add_argument("--experimental-retouch-preview", action="store_true",
                        help="Include the unvalidated Retouch preview error guard")
    parser.add_argument("--diagnostic-retouch", action="store_true",
                        help="Enable verbose native beauty initialization in a separate test APK")
    parser.add_argument("--experimental-film-log", action="store_true",
                        help="Guard LOG/Film EIS options for the paired graphics test build")
    parser.add_argument("--build-tools", type=pathlib.Path,
                        default=pathlib.Path(os.environ.get("ANDROID_HOME", str(pathlib.Path.home() / "Android/Sdk"))) / "build-tools/36.0.0")
    args = parser.parse_args()
    work = ROOT / ".cache/apk-work"
    donor_apk = ROOT / ".cache/donor/op9/proprietary/system_ext/priv-app/OplusCamera/OplusCamera.apk"
    if not work.is_dir():
        run("java", "-jar", args.apktool, "d", "-f", "-r", donor_apk, "-o", work)
    changed = 0
    for path in work.glob("smali*/**/*.smali"):
        text = path.read_text()
        result, count = re.subn(
            r"(?m)^\s*invoke-virtual \{[^\n]+\}, Lcom/oplus/uifirst/OplusUIFirstManager;"
            r"->setUxThreadValue\(IILjava/lang/String;\)V$",
            "\n    # crDroid does not implement this optional scheduling optimization.\n    nop", text)
        if count:
            path.write_text(result)
            changed += count
    if changed not in (0, 3):
        raise SystemExit(f"Unexpected donor API call count: {changed}")
    font = work / "smali/b6/k1.smali"
    original = font.read_text()
    patched, count = re.subn(
        r"(?ms)^\.method public static a\(Landroid/content/Context;\)Landroid/graphics/Typeface;\n.*?^\.end method$",
        ".method public static a(Landroid/content/Context;)Landroid/graphics/Typeface;\n"
        "    .locals 1\n"
        "    # AOSP Configuration is not an OplusBaseConfiguration.\n"
        "    sget-object v0, Landroid/graphics/Typeface;->DEFAULT:Landroid/graphics/Typeface;\n"
        "    return-object v0\n"
        ".end method", original)
    if count != 1:
        raise SystemExit("Expected exactly one OEM font configuration method")
    font.write_text(patched)
    # Keep the existing thumbnail/security checks, but launch a standard viewer
    # rather than an intent restricted to the absent OEM gallery package.
    gallery = next(work.glob("smali*/com/oplus/camera/helper/GalleryHelper.smali"))
    original = gallery.read_text()
    header = ".method public final i(Landroid/content/Intent;ZLandroid/net/Uri;)V\n"
    replacement = (header + "    .locals 1\n"
                   "    # Generic media viewer on AOSP/crDroid.\n"
                   "    const/4 v0, 0x0\n"
                   "    invoke-virtual {p1, v0}, Landroid/content/Intent;->setPackage(Ljava/lang/String;)Landroid/content/Intent;\n"
                   "    invoke-virtual {p1, v0}, Landroid/content/Intent;->setComponent(Landroid/content/ComponentName;)Landroid/content/Intent;\n"
                   "    const-string v0, \"android.intent.action.VIEW\"\n"
                   "    invoke-virtual {p1, v0}, Landroid/content/Intent;->setAction(Ljava/lang/String;)Landroid/content/Intent;\n"
                   "    const/4 v0, 0x1\n"
                   "    invoke-virtual {p1, v0}, Landroid/content/Intent;->addFlags(I)Landroid/content/Intent;\n")
    patched, count = re.subn(re.escape(header) + r"    \.locals \d+\n"
                            r"(?:    # Generic media viewer on AOSP/crDroid\.\n.*?)(?=    \.line 1\n)|"
                            + re.escape(header) + r"    \.locals 0\n",
                            lambda match: replacement, original, flags=re.S)
    if count != 1:
        raise SystemExit("Expected exactly one gallery launch method")
    gallery.write_text(patched)
    thumbnail = work / "smali/com/oplus/camera/CameraManager$e.smali"
    body = (ROOT / "patches/gallery-launch.smali").read_text().rstrip()
    patched, count = re.subn(
        r"(?ms)^\.method public final d\(Lrh/d;Lcom/oplus/camera/CameraManager\$e;\)V\n.*?^\.end method$",
        lambda match: body, thumbnail.read_text())
    if count != 1:
        raise SystemExit("Expected exactly one thumbnail gallery dispatch method")
    thumbnail.write_text(patched)
    retouch = work / "smali/y8/g.smali"
    retouch_text = patch_retouch_process(retouch.read_text(),
                                         enabled=args.experimental_retouch_preview)
    retouch.write_text(patch_retouch_logging(retouch_text, enabled=args.diagnostic_retouch))
    patch_film_options(work, enabled=args.experimental_film_log)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    run("java", "-jar", args.apktool, "b", work, "-o", output / "OplusCamera-unsigned.apk")
    normalize_apk_metadata(output / "OplusCamera-unsigned.apk", output / "OplusCamera-normalized.apk")
    keys = ROOT / ".cache/keys"
    keys.mkdir(exist_ok=True)
    key = keys / "port.p12"
    if not key.exists():
        run("keytool", "-genkeypair", "-alias", "ooscamera", "-keyalg", "RSA", "-keysize", "2048",
            "-validity", "3650", "-keystore", key, "-storepass", "ooscamera-local",
            "-keypass", "ooscamera-local", "-dname", "CN=Local OOS Camera Port", "-noprompt")
        key.chmod(0o600)
    run(args.build_tools / "zipalign", "-P", "16", "-f", "4",
        output / "OplusCamera-normalized.apk", output / "OplusCamera-aligned.apk")
    run(args.build_tools / "apksigner", "sign", "--ks", key, "--ks-key-alias", "ooscamera",
        "--ks-pass", "pass:ooscamera-local", "--key-pass", "pass:ooscamera-local",
        "--out", output / "OplusCamera.apk", output / "OplusCamera-aligned.apk")
    run(args.build_tools / "apksigner", "verify", output / "OplusCamera.apk")
    print(output / "OplusCamera.apk")


if __name__ == "__main__":
    main()
