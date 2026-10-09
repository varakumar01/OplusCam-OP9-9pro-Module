#!/usr/bin/env python3
"""Make the camera unit SDK tell the HAL which app opened the session.

Camera2Impl.createNewSession() builds the session parameters from its preview
request. A call is added just before that request is built, setting the
vendor tag com.oplus.packageName to this app's package. patch_hal.py makes
the HAL accept the tag as a session key.

    python scripts/patch_sdk.py in.jar out.jar baksmali.jar smali.jar
"""
import pathlib
import re
import subprocess
import sys
import tempfile
import zipfile

CLASS = "Lcom/oplus/ocs/camera/producer/device/Camera2Impl;"
PROXY = "Lcom/oplus/ocs/camera/metadata/parameter/CaptureRequestBuilderProxy;"
HELPER = f"""
.method private static setClientPackage({PROXY})V
    .registers 4

    new-instance v0, Landroid/hardware/camera2/CaptureRequest$Key;

    const-string v1, "com.oplus.packageName"

    const-class v2, [B

    invoke-direct {{v0, v1, v2}}, Landroid/hardware/camera2/CaptureRequest$Key;-><init>(Ljava/lang/String;Ljava/lang/Class;)V

    const-string v1, "com.oplus.camera\\u0000"

    invoke-virtual {{v1}}, Ljava/lang/String;->getBytes()[B

    move-result-object v1

    invoke-virtual {{p0, v0, v1}}, {PROXY}->setParameter(Landroid/hardware/camera2/CaptureRequest$Key;Ljava/lang/Object;)Z

    return-void
.end method
"""


def patch_smali(text):
    build = re.compile(
        r"    invoke-virtual \{(\w+)\}, " + re.escape(PROXY) + r"->build\(\)Landroid/hardware/camera2/CaptureRequest;\n\n"
        r"    move-result-object \w+\n\n"
        r"    invoke-virtual \{\w+, \w+\}, Landroid/hardware/camera2/params/SessionConfiguration;->"
        r"setSessionParameters\(Landroid/hardware/camera2/CaptureRequest;\)V\n")
    sites = build.findall(text)
    if len(sites) != 1 or "setClientPackage(" in text:
        raise SystemExit(f"Camera2Impl: expected one session parameter site, found {len(sites)}")
    call = f"    invoke-static {{{sites[0]}}}, {CLASS}->setClientPackage({PROXY})V\n\n"
    return build.sub(lambda match: call + match.group(0), text).rstrip("\n") + "\n" + HELPER


def patch_jar(source, target, baksmali, smali):
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(source) as archive:
        tmp = pathlib.Path(tmp)
        if archive.namelist() != ["classes.dex"]:
            raise SystemExit("unit SDK jar: expected a single classes.dex")
        archive.extract("classes.dex", tmp)
        subprocess.run(["java", "-jar", str(baksmali), "d", "-j", "1", str(tmp / "classes.dex"), "-o", str(tmp / "smali")],
                       check=True)
        path = tmp / "smali/com/oplus/ocs/camera/producer/device/Camera2Impl.smali"
        path.write_text(patch_smali(path.read_text()))
        subprocess.run(["java", "-jar", str(smali), "a", "-j", "1", str(tmp / "smali"), "-o", str(tmp / "out.dex")],
                       check=True)
        with zipfile.ZipFile(target, "w", zipfile.ZIP_STORED) as out:
            out.writestr(zipfile.ZipInfo("classes.dex", (1980, 1, 1, 0, 0, 0)), (tmp / "out.dex").read_bytes())


if __name__ == "__main__":
    patch_jar(*sys.argv[1:5])
