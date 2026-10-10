# Oplus Camera for the OnePlus 9 / 9 Pro

A KernelSU Next module that installs the OnePlus camera on a OnePlus 9
(`lemonade`) or 9 Pro (`lemonadep`) running **crDroid** (Android 16 or 17),
together with the camera fixes from the
[varakumar01](https://github.com/varakumar01) device trees. The installer
stops on any other ROM.

There are two builds. Pick one; they use the same module ID and cannot be
installed together.

| Build | Camera | Branch | Releases |
|---|---|---|---|
| Camera 5 | OplusCamera 5.045.451 | `main` | `v2.x.y-build<N>`, always marked latest |
| Camera 4 | OplusCamera 4.040.557 | `cam4` | `v1.x.y-cam4-build<N>` |

Download the zip from [Releases](../../releases). To switch from one build to
the other, remove the installed module and reboot first.

## What works

Tested on a OnePlus 9 (LE2111), SELinux enforcing, with crDroid 12.12
(Android 16) and crDroid 13.0 beta (Android 17). "Works" means the capture
was taken and the file was saved; image quality was only spot-checked. The
9 Pro has not been tested.

| Function | Camera 5, Android 16 | Camera 5, Android 17 | Camera 4, Android 16 | Camera 4, Android 17 |
|---|---|---|---|---|
| Photo 1x | Works | Works | Works | Works |
| Photo 0.6x (ultra-wide) | Works | Works | Works | Works |
| Photo 2x | Works | Works | Works | Works |
| Photo 5x | Works | Works | Works | Works |
| Front photo | Works | Works | Works | Works |
| Portrait, rear | Works | Works | Works | Works |
| Portrait, front | Works | Works | Not tested | Works |
| Night | Works ¹ | Works | Works ¹ | Works |
| Video 1080p 30 fps | Works | Works | Works | Works |
| Video 1080p 60 fps | Works | Works | Not tested | Works |
| Video 720p 60 fps | Works | Works | Not tested | Works |
| Video 4K 30 / 60 fps | Works | Works | Not tested | Works |
| Video 8K | Works | Works (25 fps) | Not tested | Works (25 fps) |
| Video 120 fps | Not offered | Not offered | Not tested | Not tested |
| Pro / Master | Works | Not confirmed ² | Works | Works |
| Film (Movie) | Works | Not tested | Opens, not recorded | Works |
| Time-lapse | Works | Works | Works | Works |
| Long exposure | Works ¹ | Works | Works ¹ | Works |
| XPan | Works ¹ | Works | Works ¹ | Works |
| Dual-view video | Works ¹ | Works | Works ¹ | Works |
| Tilt-shift | Works | Works | Works | Works |
| Pano | Opens, not captured | Opens, not captured | Not tested | Opens, not captured |
| Text scanner | Opens, not captured | Not tested | Not tested | Opens, not captured |
| **Slo-mo** | **Fails** ³ | **Fails** ³ | **Fails** ³ | Not retested ³ |

¹ On Android 16 these four modes were verified with an earlier form of the
same fix (a camera service that sends the client package name). The current
releases get the name to the HAL another way (see
[aox/README.md](aox/README.md)); that method was run on Android 17 only.

² The capture did not save in the Android 17 run. The same thing happened
once on Android 16 and a second attempt worked, so this is probably the test
and not the mode.

³ Opening Slo-mo stops the camera provider, and the app then reopens in
Slo-mo and stops again. **Do not open Slo-mo.** To recover, clear the camera
app's data. Not solved.

Other known faults, seen with Camera 5 on a ROM built from the same trees:
RAW in Master mode saves a 0-byte file and locks the shutter, the Fresh and
Emerald film filters save black photos, and 10-bit HEIC is not usable.

One kernel crash dump happened on Android 17 during testing, on a reboot
shortly after Slo-mo had stopped the camera provider. The crash record was
lost, so the cause is not known.

## Install

In KernelSU Next: **Modules → Install**, pick `OplusCamera-OP9-<version>.zip`,
reboot. Open Oplus Camera and grant its permissions. No Mountify or other
mounting module is needed.

The camera has to see the module's files, which KernelSU hides from apps by
default. After the reboot the module turns **Umount modules** off for the
camera and for the launcher by itself, and puts both profiles back when it is
disabled or removed. It does not grant root to anything. If the installer says
this KernelSU has no app profile interface it can use, or the camera closes
as soon as it opens, set it by hand: **App Profile → Oplus Camera → Custom →
Umount modules** off, root access off. What the module did is in
`/data/adb/modules/ooscamera_op9/visibility.log`.

The installer stops, and says why, when the ROM is not crDroid, the phone is
not a OnePlus 9 / 9 Pro, Android is older than 16, `oplus-fwk.jar` or OverlayFS is missing, another
camera version of this module is installed, or the
camera could not be made to start on this ROM. The reasons are kept in
`/data/local/tmp/ooscamera-install.log`. After a successful install the
decisions are in `/data/adb/modules/ooscamera_op9/aox.log` and the mounts in
`mount.log` next to it.

## Download

Every push to `main` or `cam4` is built by `.github/workflows/build.yml` and
published under Releases (`v<version>-build<N>`) with the module zip and its
SHA-256 attached. Each camera keeps one release: a new build replaces that
camera's previous one. The Camera 5 release is always the one marked latest.

## How it mounts

The installer packs the payload into an ext4 image inside the module,
keeping the SELinux labels the camera libraries need. `post-fs-data.sh`
mounts it read-only and lays one read-only overlay over each system
directory the payload has files for, before Android scans apps and
permissions. Nothing is written to a system partition. `skip_mount` keeps
other mounting backends from mounting the payload twice.

If a mount fails, the overlays are rolled back and the module disables
itself. If a boot does not complete, the module is disabled on the next one.
Disabling or removing the module and rebooting removes everything; photos
are not touched.

## Build

See [aox/README.md](aox/README.md#build). `scripts/audit_artifact.py` checks
a finished ZIP against its payload allowlist and checksums.

## Credits

- [varakumar01](https://github.com/varakumar01)

## License

The scripts and module files in this repository are licensed under the
[GNU General Public License v3.0](LICENSE). Three files carry their own SPDX
header and keep that license: `native/ksu_visibility.c` and
`tests/visibility_policy_device.c` (GPL-2.0-only), and
`native/uah-client/uah_client.c` (Apache-2.0).

The camera and its native libraries are proprietary OEM binaries. They are
not in this repository and the license above does not cover them; nothing
here claims they are open source or freely redistributable.
