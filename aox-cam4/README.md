# aox-cam4 camera changes

This module carries the camera work from the `aox-cam4` branches, 2026-09-30 to 2026-10-06. It is meant for OnePlus 9 / 9 Pro ROMs that were not built from those branches. Only camera changes are included. The aox-cam4 camera work is by
[varakumar01](https://github.com/varakumar01).

| Repository (aox-cam4) | Pinned revision |
|---|---|
| varakumar01/proprietary_vendor_oneplus_lemonade | `909a41d` (base `f7ae875`) |
| varakumar01/android_device_oneplus_lemonade | `09a7223` |
| varakumar01/android_hardware_oplus | `fc0d19d` |
| varakumar01/android_device_oneplus_sm8350-common | `86c49b7` |

Pairs of commits that were later reverted cancel out and are left out: the urcc HAL stack, 4K/120fps exclusivity and 4K60 main-sensor-only.

## What the module applies

Every change is conditional, and the installer logs each decision to `/data/adb/modules/ooscamera_op9/aox-cam4.log`. If the module already ships a file or sets a value, the module's version wins. If the device already has a file, the device copy stays unless the change was made against that exact file.

| Change | Commits | How it is applied |
|---|---|---|
| 34 camera algorithm/JNI libraries (Anc*, 2DSlender, aisd, FDClite, SuperText/XDoc/YTCommon, npu, long exposure, ui-oplus, …) | vendor 2b2f3d2, 02d1aaf, 6b5994f, 9beeb6a, 3ddae90 | Added only when `/odm/lib64` lacks them, and only if every DT_NEEDED library exists on the device. A library whose dependency is missing is dropped, and so is anything that depends on it. |
| `libnightvision.so` with luma spatial noise reduction | vendor 909a41d, device 09a7223 | Added when missing. Replaces the device copy only if that copy is the unpatched stock build. |
| `libEIS.so` linked against the stock `libui-oplus.so` | vendor 3ddae90, device 25d682a | Replaces only the stock `libEIS.so` this change was made from. |
| 32-bit `libcamxexternalformatutils.so` | vendor 00e6950 | Added when `/vendor/lib` lacks it. |
| ArcSoft HVX skels with their original SONAME | vendor d1fd799 | Replace only the SONAME-rewritten copies. Uses a new `/odm/lib/rfsa/adsp` overlay, which is mounted only when needed. |
| `camera_unit_feature_config.protobuf` (120fps not forcing 4K) | vendor 907126e | Replaces only the exact file the change was made from. |
| `oplus_camera_config`: 4K60 advertisement, 4K focus tracking, Text Scanner mode, recorder surface release | vendor 1acc28e, 74562fa, 86876a2, 719c4b4 | Install-time edits of the module's copy, else the device's copy. Missing tags are appended. |
| `oplus_camera_aps_config`: hardware JPEG encoder | vendor dcc919d | Install-time edit. |
| `CameraHWConfiguration.config`: keep main sensor streaming below 1x, ultrawide active map, 60fps zoom down to the ultrawide | vendor 66d4b9a | Install-time edits. A value is changed only if it is still the stock one. The 60fps minimum zoom follows this device's own video zoom range. |
| `camera_unit_config`: `video_120fps` mapped to constrained high speed and added to rear_main's video table | vendor 5b514cd, d954b5c | Exact blocks, applied together or not at all. |
| AAC encoder cap raised to 288 kbps (audio track of camera video) | device 7c8d1f0 | The device's media profiles file is edited and bind-mounted in post-fs-data. |
| `liboplus-uah-client.so`: camera scene hints sent to the power HAL | hardware 238ddc9, common 2277dd9 | Built from `native/uah-client`. Used when the device has no client or has the LineageOS no-op stub. A stock OEM client, which links libuahcore/liburcccore, is never replaced. |
| sepolicy: `hal_camera_default` as a power HAL client; `/proc/OIS` labelled `vendor_proc_camera` | hardware fc0d19d, 96d618c | `sepolicy.rule` |

The edit definitions live in `module/aox-cam4/edits.txt` and `module/aox-cam4/blocks/`. The pinned library list is `aox-cam4/manifest.json`.

## Camera changes a module cannot carry

These need a ROM rebuild:
- camera-provider init override adding group `oem_2907` for the thermal-engine sockets (common 1e69579). init reads its rc files before modules are mounted.
- `frameworks_base` camera2 high-speed fps range fix (common c365a60). This is a boot JAR and differs per ROM.
- `frameworks_native` libnativewindow P010_VENUS chroma planes (common 86c49b7). This is a system library that differs per ROM.

The branches' non-camera work (display, audio HAL, settings, diagnostics, apps) is out of scope here.

## Build

```sh
python scripts/prepare_aox_cam4.py            # fetch + verify the pinned libraries
sh native/uah-client/build.sh .cache/aox-cam4/liboplus-uah-client.so   # clang + ld.lld
python scripts/build.py ... --aox-cam4-cache .cache/aox-cam4 \
  --uah-client .cache/aox-cam4/liboplus-uah-client.so
```

Host tests: `python scripts/prepare_aox_cam4.py --fixtures`, then `python -m pytest tests/test_aox_cam4.py`. The tests need BusyBox, plus clang/lld and host libc++ for the uah client checks.
