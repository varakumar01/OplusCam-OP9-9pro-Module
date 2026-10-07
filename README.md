# OnePlus 9 / 9 Pro OOS Camera port

**v1.0.0:** the installer now accepts OnePlus 9 (`lemonade`) and
9 Pro (`lemonadep`) on any ROM that ships `oplus-fwk.jar`, not only crDroid.
It also carries the `aox-cam4` camera work (2026-09-30 to 2026-10-06) for
ROMs that lack it: camera libraries, config edits applied at install time,
power-HAL scene hints and camera sepolicy. Each change applies only where it
matches the device. See [aox-cam4/README.md](aox-cam4/README.md) for what is
included, how each piece is applied, and which changes still need a ROM
rebuild.

**CI builds:** every push to `main` runs `.github/workflows/build.yml`. It runs
the tests and publishes `ooscamera-op9-<version>.zip` as a GitHub prerelease
(`v<version>-build<N>`, under Releases) and as a workflow artifact. That ZIP is the generic build from pinned public
sources. It contains no device-collected libraries (`--native-cache`), patched
APK or blur engine, so Night (starburst labels), Front Portrait and Pro white
balance behave as in the unpatched donor. Use the full build below for those.
This snapshot includes experimental work; release instructions below describe
the historical 0.7.0 build, not all current candidate changes.

Experimental local port for **crDroid 12.12 / Android 16**, OnePlus 9 Pro
(`lemonadep`, LE2123), KernelSU Next 3.2.0. The installer accepts SDK 36 and newer;
Android 17 / SDK 37 and later are experimental, not validated on this phone.

Version 0.7 includes camera-only fixes for the missing OEM thread scheduler and
font configuration APIs. It also includes 95 unchanged libraries collected from
this phone's firmware, with `same_process_hal_file` labels so the camera can load
them. Two starburst libraries required these labels to fix Night's green preview.
Video's OEM automatic lens switching is disabled to avoid a HAL buffer stall.
Video blur now includes its missing native engine and a private GPU loader;
preview and 1080p recording were tested at approximately 30 fps. Saved main, Night, ultrawide and front JPEGs, plus
1080p/30 and 4K/30 MP4s with audio, were validated after reboot. The 3.3x test used the main sensor for the
close subject; optical telephoto and advanced modes remain unverified. This
archive is specific to the firmware on this phone.

Version 0.7 fixes Front Portrait's missing Qualcomm JNI alias and the donor's
program-header mapping, without changing its executable code. Front Portrait
preview and a saved 3456 x 4608 JPEG were verified on Android 16; portrait
segmentation quality still needs testing with a person. Pro white balance now
uses the firmware's manual-temperature override with AWB enabled, and returning
to Auto clears that override. Preview and saved JPEG colour changes were
verified at 3300 K and 6700 K. The edited SDK is an app library, not a boot JAR.

**Still unresolved:** Slow motion crashes the vendor camera provider; Long
exposure, Hi-res and 1:1 Photo reject their stream configuration on
the Android 16 test phone. Android 17 testers also report Dual-view video, LOG,
Retouch, other non-4:3 ratios and holding the Photo shutter to record as unsafe. These are not fixes
in 0.7; avoid those controls while investigation continues. Pro RAW has a
tester-reported pink cast and is not validated. Do not infer working recording
frame rates or resolution from menu options alone.

The thumbnail opens the selected media in an installed Android viewer. Capture
filters use the OEM wrapper with its unused logging dependency removed; that
dependency caused crashes during zoom/mode changes in version 0.4.

The first module packages a pinned OP9-targeted donor, adds the camera as a
privileged app, registers its SDK libraries, and exempts only the camera package
from hidden-API enforcement. It does not modify the boot image or replace the
existing crDroid OPlus framework JAR. APK version: 4.020.35.

## Build

Requires Python 3, Git and ADB. Donor binaries remain in the ignored cache.

```sh
mkdir -p .cache/donor
git clone https://github.com/dev-sm8350/vendor_oplus_camera .cache/donor/op9
git -C .cache/donor/op9 checkout 6e7d1e0bb6b242cf58ae152152d011e846bf812e
python scripts/build.py
```

For the current patched, device-specific build, also install Apktool 3.0.3 at
`.cache/tools/apktool.jar`, Java, and Android SDK Build Tools 36.0.0, then run:

```sh
python scripts/patch_apk.py
python scripts/patch_sdk.py
python scripts/native_access.py collect
python scripts/build.py --apk build/OplusCamera.apk \
  --sdk build/com.oplus.camera.unit.sdk.jar \
  --native-cache .cache/device/vendor_camera \
  --filter-cache .cache/donor/filter \
  --blur-cache .cache/donor/blur/porsche \
  --camera-config .cache/device/camera-config-video-main.json
```

The native manifest additionally contains `lib_oplus_starburst_capture.so` and
`lib_oplus_starburst_preview.so`, collected from `/odm/lib64` on this phone.
The configuration override copies `/odm/etc/camera/config/oplus_camera_config`
and sets only `com.oplus.feature.video.sat.support` to `0`. Preserve the signing
key in `.cache/keys/port.p12` for subsequent APK updates.

`--filter-cache` fetches and verifies the pinned OnePlus 11 OEM
`libFilterWrapper.so` from
[TheMuppets' vendor tree](https://github.com/TheMuppets/proprietary_vendor_oneplus_salami/tree/2ae5c2548d5150b9948ddec33f9b5bbb2f07fd66).
This restores the capture-filter entry points missing from this ROM and uses the
existing device Polarr renderer. The builder removes its unused `libalog.so`
dependency without changing executable code: that library's background logger
crashed during zoom/mode changes. Original and installed hashes, the edit and
source revision are recorded separately in `filter-source.json`.

`--blur-cache` fetches two verified OEM blur libraries from the pinned
[Realme vendor tree](https://github.com/resist15/vendor_realme_porsche/tree/8bdc52979f0fe9f424a92b62b7bf0c72e52b4c76).
The engine's dynamic loader name is changed to `liboosb_loader.so`. That private
copy of the verified device SNPE loader requests GPU_FLOAT16 through its existing
availability check and retains its CPU fallback. The original loader used by
other camera processing is unchanged. Source and installed hashes and both
edits are recorded in `blur-source.json`. Original device model files are kept;
an experiment with the donor model did not solve CPU fallback and was rejected.
This restores preview/recording stability and frame rate; subject separation
and blur quality still need testing with a person in frame.

Output: `build/ooscamera-op9-0.7.0.zip` (version read from `module.prop`), with
a SHA-256 sidecar and payload checksum/provenance manifest.
`build/ooscamera-op9.zip` points to the latest build for the existing commands.
The builder verifies the donor revision and reconstructed camera APK SHA-256,
rejects unresolved Git LFS pointers, and checks APK ZIP integrity.

## Shareable artifact metadata

The module and rebuilt APK use fixed ZIP timestamps and omit ZIP comments and
host filesystem metadata. The public native manifest includes only firmware
paths, labels, sizes and hashes; local collection diagnostics are excluded.
The APK certificate has a generic subject (`CN=Local OOS Camera Port`), and the
private signing key stays in the ignored cache. Reusing that certificate keeps
updates compatible, but also makes releases signed with it linkable to one
another. Firmware hashes and source revision pins remain in the artifact.

Audit the finished module, including decompressed APK/JAR contents:

```sh
python scripts/audit_artifact.py build/ooscamera-op9.zip \
  --identifiers-file .cache/privacy/sensitive-identifiers.txt \
  --report .cache/privacy/final-audit.json
```

The private identifiers file contains one known name, address, device identifier
or local path per line. Keep it outside the public source and archive. The audit
checks UTF-8 and UTF-16 representations without printing the identifiers,
validates payload allowlists and metadata schemas, checks file hashes and looks
for private-key blocks. It does not promise that unknown identifiers or binary
data can never contain identifying information. Do not package device logs,
photos, app data, calibration dumps or signing keys with the release.

## Install

In KernelSU Next, open **Modules → Install**, select
`ooscamera-op9-0.7.0.zip`, then reboot. Open OOS Camera and grant camera,
microphone and media permissions when prompted. In KernelSU Next's **App Profile**
for **OOS Camera / com.oplus.camera**, turn off **Umount modules** (use a custom
non-root profile if the default profile hides this switch). Leave root access
disabled. This is a one-time setting: the camera must see its systemless SDK and
libraries. No Mountify, separate mounting backend or ADB is required.
The installer checks the ROM, Android version, OverlayFS support and camera
mounts; unsupported configurations stop installation.

Users upgrading from 0.5 can install this ZIP over the existing camera module.
If Mountify is your active mounting backend, keep it enabled during installation:
KernelSU blocks module installs while a registered backend is disabled. If no
other module needs Mountify, uninstall it and reboot before installing this ZIP.
Otherwise keep it enabled; this camera uses its own mounts. The camera installer
does not modify or remove other modules.

## Collect failures

USB debugging and root authorization for ADB shell are required for diagnostics.

```sh
python scripts/device.py install
adb reboot
# Unlock the phone after startup.
python scripts/device.py launch
python scripts/device.py collect
```

Diagnostics are stored under `.cache/device/`, excluded from Git because device
logs can contain personal information. Existing camera apps are retained.

### Standalone mounting

The installer prepares a private ext4 image inside the module, preserving the
camera libraries' SELinux labels, and removes the redundant unpacked payload.
This kernel rejects OverlayFS lower directories on encrypted F2FS, and its
tmpfs does not support the required labels; ext4 avoids both limitations.
Preparation takes place once per installation, rather than copying the payload
each boot. Installation temporarily requires extra free space for that image.

`post-fs-data.sh` mounts the image read-only and applies ten read-only,
camera-specific overlays before Android scans privileged apps and permissions.
The overlays merge original system files; they do not write system partitions.
Their source name is `KSU`, as required for KernelSU's mount removal support.
`skip_mount` prevents standard mounting backends from mounting the payload a
second time. The camera remains a regular module, leaving the single metamodule
slot available for other modules. No global mounting configuration is changed.
KernelSU's default per-app mount hiding removes these overlays from camera
processes unless the camera's **Umount modules** setting is off. Its profile
API is restricted to the manager, so the module does not bypass that protection
or edit KernelSU's private profile database. See the
[non-root App Profile guide](https://kernelsu.org/guide/app-profile.html#non-root-profile).

Mount failures roll back the camera overlays and disable the module. An
interrupted boot disables the camera on the next boot; `boot-completed.sh`
clears the pending marker after a successful boot. Local mount results are in
`/data/adb/modules/ooscamera_op9/mount.log`. Images and state live inside the
module and are removed by KernelSU on uninstall. Disable or uninstall followed
by reboot removes the camera mounts.

These lifecycle choices follow the [KernelSU module guide](https://kernelsu.org/guide/module.html)
and [KernelSU Next mounting guide](https://github.com/KernelSU-Next/KernelSU-Next/blob/dev/website/docs/guide/metamodule.md).
The tracked Mountify patch records the older setup and is no longer required.

## Disable

```sh
python scripts/device.py disable
adb reboot
```

Alternatively disable **OOS Camera — OnePlus 9 Pro prototype** in KernelSU Next.
Older installations can also disable Mountify if no other module needs it. If normal startup fails but rooted ADB is available:

```sh
python scripts/device.py root 'touch /data/adb/modules/ooscamera_op9/disable'
adb reboot
```

The baseline APK was also installed normally during initial diagnostics.
After disabling the module, remove that test installation with
`adb uninstall com.oplus.camera` if it remains. Neither disabling nor removing
this module deletes photos from shared storage.

## Credits

- [varakumar01](https://github.com/varakumar01)

The camera and native components are proprietary OEM binaries. This repository
contains packaging and diagnostic scripts, not a claim that those binaries are
open source or generally redistributable.
