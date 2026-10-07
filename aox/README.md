# What the module carries from the aox branch

Camera work from the `aox` branches of the OnePlus 9 / 9 Pro trees, for ROMs
that were not built from them. The exact revisions and every file's SHA-256
are in [manifest.json](manifest.json); `scripts/gen_manifest.py` regenerates
it from local clones.

| Tree | What is taken |
|---|---|
| varakumar01/vendor_oplus_camera | OplusCamera 5.045.451, both unit SDK jars, the support wrapper, 39 JNI libraries |
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
| no system OplusCamera | the module installs 5.045.451 in `/system_ext/priv-app/OplusCamera` |
| 5.045.451 or newer | the ROM's app, SDK jars and paired libraries stay; only the fixes below apply |
| older | the module's APK is overlaid at the ROM's own path and file name (`/system`, `/system_ext` or `/product` `priv-app`; anywhere else stops the install) |

The module's APK is signed with the public AOSP platform test key. On a
test-keys ROM that makes it platform-signed, as it is in an aox build.

Four `/odm/lib64` libraries are paired with the 5.x app and replace the
device copies whenever the module's app is in use: `libAlgoInterface`,
`libAlgoProcess`, `libPreviewDecisionOld`, `libFilterWrapper`. If one of them
cannot be installed (a DT_NEEDED library missing on the ROM), the install
stops rather than leaving an app that cannot start.

## oplus-fwk

5.x needs classes that older `oplus-fwk.jar` builds lack. The installer looks
for three of them in the ROM's `/system/framework/oplus-fwk.jar`. If any is
missing, the module overlays its own jar, built from
`android_hardware_oplus` at the pinned revision plus the three classes in
`fwk/`, which AxionOS keeps in `frameworks/base` and other ROMs lack. This replaces a boot jar:
the first boot is slower, and another app on that ROM that relies on a class
only its own `oplus-fwk` had would break. If that boot does not complete,
the module disables itself on the next one.

## Fixes

Every change is conditional and logged to
`/data/adb/modules/ooscamera_op9/aox.log`. A file the device already has
stays unless the change was made against that exact file.

| Change | How it is applied |
|---|---|
| 37 camera algorithm libraries in `/odm/lib64` (Anc*, 2DSlender, aisd, FDClite, SuperText/XDoc/YTCommon, npu, long exposure, ui-oplus, aideblur, msnativefilter, extendfile, …) | Added when missing, and only if every DT_NEEDED library exists. A library whose dependency is missing is dropped, and so is anything that depends on it. |
| 68 `meishe_lut` and 6 `filters_lut` tables, the self-bokeh model | Added when missing. |
| `libnightvision.so` with luma spatial noise reduction | Added when missing; replaces only the unpatched stock build. |
| `libEIS.so` linked against the stock `libui-oplus.so` | Replaces only the stock `libEIS.so`. |
| 32-bit `libcamxexternalformatutils.so` | Added when `/vendor/lib` lacks it. |
| ArcSoft HVX skels with their original SONAME | Replace only the SONAME-rewritten copies. |
| `camera_unit_feature_config.protobuf` (120fps not forcing 4K, Live Photo) | One build per phone; replaces only the stock file or the earlier aox one. |
| `oplus_camera_config`: 45 tags (43 on the 9 Pro) | Install-time edits; missing tags are appended. |
| `CameraHWConfiguration.config`: ultrawide active map; on the 9 also the main sensor kept streaming below 1x and 60fps zoom down to the ultrawide | Install-time edits; a value is changed only if it is still the stock one. |
| `camera_unit_config`: the APS JNI version; on the 9 `video_120fps` in rear_main's video table | A key insert, and two exact blocks applied together or not at all. |
| AAC encoder cap raised to 288 kbps | The media profiles file is edited and bind-mounted in post-fs-data. |
| `liboplus-uah-client.so`: camera scene hints sent to the power HAL | Built from `native/uah-client`. Never replaces a stock OEM client. |
| sepolicy: camera provider as power HAL client and wakelock holder; `/proc/OIS` label | `sepolicy.rule` |
| `/data/vendor/camera_process` for Live Photo | Created in post-fs-data. |

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
- running the app in its own `opluscamera_app` SELinux domain.

## Known faults of 5.045.451 on these phones

Seen on the OnePlus 9 with an aox build; the module does not change them:
RAW (Master mode) saves a 0-byte file and locks the shutter; the Fresh and
Emerald film filters save black photos; 10-bit HEIC is not usable.

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
