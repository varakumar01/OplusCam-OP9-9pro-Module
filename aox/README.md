# What the module carries from the aox branch

Camera work from the `aox-cam4` branches of the OnePlus 9 / 9 Pro trees, for ROMs
that were not built from them. The exact revisions and every file's SHA-256
are in [manifest.json](manifest.json); `scripts/gen_manifest.py` regenerates
it from local clones.

| Tree | What is taken |
|---|---|
| varakumar01/vendor_oplus_camera | OplusCamera 4.040.557, both unit SDK jars, the support wrapper, 35 JNI libraries |
| varakumar01/proprietary_vendor_oneplus_lemonade, `_lemonadep` | `/odm` libraries, filter tables, models, the feature protobuf; the config changes as edits |
| varakumar01/android_hardware_oplus | `oplus-fwk`, the uah client, camera sepolicy |
| varakumar01/android_device_oneplus_lemonade | the AAC encoder cap |

The APK already contains the four aox app patches: real-time 120fps at
720p/1080p/4K, Ultra Night Video recorded from the processed preview, the
thumbnail opening Glimpse, and Edit open to any editor.

## The camera app

The installer asks the package manager for the system copy of
`com.oplus.camera`:

| ROM state | What happens |
|---|---|
| no system OplusCamera | the module installs 4.040.557 in `/system_ext/priv-app/OplusCamera` |
| 4.040.557 or newer | the ROM's app, SDK jars and paired libraries stay; only the fixes below apply |
| older | the module's APK is overlaid at the ROM's own path and file name (`/system`, `/system_ext` or `/product` `priv-app`; anywhere else stops the install) |

The module's APK is signed with the public AOSP platform test key. On a
test-keys ROM that makes it platform-signed, as it is in an aox build.

OplusCamera 4.x runs on the stock `/odm` libraries, so nothing is paired with
the app, and it uses the ROM's own `oplus-fwk.jar`.

## Fixes

Every change is conditional and logged to
`/data/adb/modules/ooscamera_op9/aox.log`. A file the device already has
stays unless the change was made against that exact file.

| Change | How it is applied |
|---|---|
| 35 camera algorithm libraries in `/odm/lib64` (Anc*, 2DSlender, aisd, FDClite, SuperText/XDoc/YTCommon, npu, long exposure, ui-oplus, …) | Added when missing, and only if every DT_NEEDED library exists. A library whose dependency is missing is dropped, and so is anything that depends on it. |
| `libnightvision.so` with luma spatial noise reduction | Added when missing; replaces only the unpatched stock build. |
| `libEIS.so` linked against the stock `libui-oplus.so` | Replaces only the stock `libEIS.so`. |
| 32-bit `libcamxexternalformatutils.so` | Added when `/vendor/lib` lacks it. |
| ArcSoft HVX skels with their original SONAME | Replace only the SONAME-rewritten copies. |
| `camera_unit_feature_config.protobuf` (120fps not forcing 4K) | One build per phone; replaces only the stock file or the earlier aox one. |
| `oplus_camera_config`: 4 tags (3 on the 9 Pro); `oplus_camera_aps_config`: the hardware JPEG tag | Install-time edits; missing tags are appended. |
| `CameraHWConfiguration.config`: ultrawide active map; on the 9 also the main sensor kept streaming below 1x and 60fps zoom down to the ultrawide | Install-time edits; a value is changed only if it is still the stock one. |
| `camera_unit_config`: on the 9 `video_120fps` in rear_main's video table | Two exact blocks applied together or not at all. |
| AAC encoder cap raised to 288 kbps | The media profiles file is edited and bind-mounted in post-fs-data. |
| `liboplus-uah-client.so`: camera scene hints sent to the power HAL | Built from `native/uah-client`. Never replaces a stock OEM client. |
| sepolicy: camera provider as power HAL client and wakelock holder; `/proc/OIS` label | `sepolicy.rule` |
| sepolicy: the app's access to `vendor_file` libraries, `/data/vendor/camera*`, the camera provider and its postproc service, osense | `sepolicy.rule`, for `priv_app` and `priv_app_36`. Every app in those domains gets it. |
| `/data/vendor/camera_process` for the APS job store | Created and labelled in post-fs-data. |

Reinstalling or updating the module: files the running copy already overlays
are provided again, since the ROM's own file is hidden behind them.

## What a module cannot carry

These need a ROM built from the aox trees:
- the camera2 high-speed fps range fix and the vendor-tag lookup cache in
  `frameworks/base` (boot jar, differs per ROM). Without the first, 4K 120fps
  may not record at 120.
- `libnativewindow` returning chroma planes for QTI P010_VENUS buffers.
  Without it Movie mode LOG / HDR can crash.
- the thermal client group on the camera provider service (init reads its rc
  files before modules are mounted).
- running the app in its own `opluscamera_app` SELinux domain, and the
  `same_process_hal_file` label on the ROM's own camera libraries; the rules
  above stand in for both.

## Known faults of 4.040.557 on these phones

Night, Long exposure, XPan and Dual-view video need a ROM whose camera
service sends the camera HAL the client package name (`camera.package_name`
soong config). crDroid 12.12 does not.

## Build

```sh
python scripts/prepare_aox.py                 # fetch + verify everything pinned
sh native/uah-client/build.sh .cache/aox/liboplus-uah-client.so   # clang + ld.lld
cd scripts && python build.py --uah-client ../.cache/aox/liboplus-uah-client.so
```

`build.py` needs `apksigner` (Android SDK Build Tools; `--apksigner` to point
at it). Host tests: `python scripts/prepare_aox.py --fixtures`, then
`python -m pytest tests`. They need BusyBox, `apksigner`, and clang/lld with
host libc++ for the uah client checks.
