# OOS Camera for the OnePlus 9 / 9 Pro

A KernelSU Next module that installs **OplusCamera 5.045.451** on a OnePlus 9
(`lemonade`) or 9 Pro (`lemonadep`) running an Android 16+ ROM that has
`oplus-fwk.jar`, together with the camera fixes from the `aox` branch of the
[varakumar01](https://github.com/varakumar01) device trees.

- If the ROM already ships this camera or a newer one, the app is left alone
  and only the fixes are applied.
- If the ROM ships an older one, it is replaced in place.
- If the ROM's `oplus-fwk.jar` is too old for 5.x, the module overlays its own.

[aox/README.md](aox/README.md) lists every change, how each is applied, what
a module cannot carry and the known faults of this camera version.

**Status:** built and host-tested only. Version 2.0.0 has not been installed
on a phone yet; the 9 Pro path has never run on a 9 Pro.

## Install

In KernelSU Next: **Modules → Install**, pick `ooscamera-op9-<version>.zip`,
reboot. Open OOS Camera and grant its permissions. In **App Profile → OOS
Camera** turn **Umount modules** off and leave root access off: the camera
has to see the module's files. No Mountify or other mounting module is
needed.

The installer stops, and says why, when the phone is not a OnePlus 9 / 9 Pro,
Android is older than 16, `oplus-fwk.jar` or OverlayFS is missing, or the
camera could not be made to start on this ROM. The reasons are kept in
`/data/local/tmp/ooscamera-install.log`. After a successful install the
decisions are in `/data/adb/modules/ooscamera_op9/aox.log` and the mounts in
`mount.log` next to it.

## Download

Every push to `main` is built by `.github/workflows/build.yml` and published
under Releases as a prerelease (`v<version>-build<N>`).

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
