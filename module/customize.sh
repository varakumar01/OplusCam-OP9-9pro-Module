#!/system/bin/sh
[ "$KSU" = "true" ] || abort "This prototype requires KernelSU Next."
# OnePlus 9 (lemonade) and 9 Pro (lemonadep), any ROM: AOSP-based ROMs use the
# codename, OxygenOS-derived builds the marketing name.
camera_device=
for prop in ro.product.vendor.device ro.product.device ro.build.product ro.crdroid.device; do
    case "$(getprop "$prop")" in
        lemonade|lemonadep|OnePlus9|OnePlus9Pro) camera_device=$(getprop "$prop"); break ;;
    esac
done
[ -n "$camera_device" ] || abort "Expected a OnePlus 9 or OnePlus 9 Pro."
ui_print "Device: $camera_device"
case "$camera_device" in
    lemonadep|OnePlus9Pro) AOX_DEVICE=lemonadep ;;
    *) AOX_DEVICE=lemonade ;;
esac
CAMERA_SDK=$(getprop ro.build.version.sdk)
case "$CAMERA_SDK" in
    ''|*[!0-9]*) abort "Cannot determine Android SDK version." ;;
esac
[ "$CAMERA_SDK" -ge 36 ] || abort "Requires Android 16 / SDK 36 or newer."
if [ "$CAMERA_SDK" -gt 36 ]; then
    ui_print "SDK $CAMERA_SDK: newer Android support is experimental."
fi
[ -f /system/framework/oplus-fwk.jar ] || abort "Missing OPlus compatibility framework (oplus-fwk.jar)."
[ -x /system/bin/mkfs.ext4 ] || abort "Missing ext4 filesystem tools."
grep -qw overlay /proc/filesystems || abort "This kernel needs OverlayFS support."
if [ -f "$MODPATH/gralloc-source.json" ]; then
    CAMERA_GRALLOC_SOURCE=$(sed -n 's/.*"source_sha256": "\([0-9a-f]*\)".*/\1/p' "$MODPATH/gralloc-source.json")
    CAMERA_GRALLOC_PATCHED=$(sed -n 's/.*"patched_sha256": "\([0-9a-f]*\)".*/\1/p' "$MODPATH/gralloc-source.json")
    [ "${#CAMERA_GRALLOC_SOURCE}" -eq 64 ] && [ "${#CAMERA_GRALLOC_PATCHED}" -eq 64 ] || abort "Invalid graphics trial manifest."
    CAMERA_GRALLOC_PREVIOUS=$(sed -n 's/.*"previous_patched_sha256": "\([0-9a-f]*\)".*/\1/p' "$MODPATH/gralloc-source.json")
    [ "${#CAMERA_GRALLOC_PREVIOUS}" -eq 64 ] || abort "Invalid previous graphics trial checksum."
    CAMERA_GRALLOC_CURRENT=$(sha256sum /vendor/lib64/libgrallocutils.so | cut -d ' ' -f 1)
    case "$CAMERA_GRALLOC_CURRENT" in
        "$CAMERA_GRALLOC_SOURCE"|"$CAMERA_GRALLOC_PATCHED"|"$CAMERA_GRALLOC_PREVIOUS") ;;
        *) abort "Graphics trial does not match this ROM library; installation cancelled." ;;
    esac
    ui_print "Graphics format trial: only legacy 10-bit camera requests are changed."
fi
if [ -f "$MODPATH/gralloc32-source.json" ]; then
    [ -f "$MODPATH/gralloc-source.json" ] || abort "ARMv7 graphics trial requires ARM64 graphics trial."
    CAMERA_GRALLOC32_SOURCE=$(sed -n 's/.*"source_sha256": "\([0-9a-f]*\)".*/\1/p' "$MODPATH/gralloc32-source.json")
    CAMERA_GRALLOC32_PATCHED=$(sed -n 's/.*"patched_sha256": "\([0-9a-f]*\)".*/\1/p' "$MODPATH/gralloc32-source.json")
    CAMERA_GRALLOC32_PREVIOUS=$(sed -n 's/.*"previous_patched_sha256": "\([0-9a-f]*\)".*/\1/p' "$MODPATH/gralloc32-source.json")
    [ "${#CAMERA_GRALLOC32_SOURCE}" -eq 64 ] && [ "${#CAMERA_GRALLOC32_PATCHED}" -eq 64 ] || abort "Invalid ARMv7 graphics trial manifest."
    [ "${#CAMERA_GRALLOC32_PREVIOUS}" -eq 64 ] || abort "Invalid previous ARMv7 graphics trial checksum."
    CAMERA_GRALLOC32_CURRENT=$(sha256sum /vendor/lib/libgrallocutils.so | cut -d ' ' -f 1)
    case "$CAMERA_GRALLOC32_CURRENT" in
        "$CAMERA_GRALLOC32_SOURCE"|"$CAMERA_GRALLOC32_PATCHED"|"$CAMERA_GRALLOC32_PREVIOUS") ;;
        *) abort "ARMv7 graphics trial does not match this ROM library; installation cancelled." ;;
    esac
    ui_print "Matching ARMv7 graphics trial for media services."
fi
ui_print "Installing OOS Camera for the OnePlus 9 / 9 Pro."
ui_print "Standalone mounting: Mountify is not required."
ui_print "A reboot is required for system permissions and library discovery."
if [ -f "$MODPATH/ksu-visibility" ]; then
    set_perm "$MODPATH/ksu-visibility" 0 0 0700
    "$MODPATH/ksu-visibility" check || abort "KernelSU profile interface unavailable; automatic camera setup cannot run."
fi
if [ -f "$MODPATH/aox.sh" ]; then
    # shellcheck source=module/aox.sh
    . "$MODPATH/aox.sh"
    if ! aox_install; then
        # The module directory is discarded on failure; keep the reasons.
        cp "$MODPATH/aox.log" /data/local/tmp/ooscamera-install.log 2>/dev/null
        abort "$(grep -E '^(fail|app) ' "$MODPATH/aox.log" | tail -n 1 | cut -c 7-) (log: /data/local/tmp/ooscamera-install.log)"
    fi
fi
set_perm_recursive "$MODPATH" 0 0 0755 0644
set_perm "$MODPATH/post-fs-data.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/boot-completed.sh" 0 0 0755
set_perm "$MODPATH/mount-camera.sh" 0 0 0755
if [ -f "$MODPATH/ksu-visibility" ]; then
    set_perm "$MODPATH/ksu-visibility" 0 0 0700
    set_perm "$MODPATH/service.sh" 0 0 0755
    set_perm "$MODPATH/uninstall.sh" 0 0 0755
fi
set_perm_recursive "$MODPATH/system" 0 0 0755 0644 u:object_r:system_file:s0
if [ -f "$MODPATH/native-labels.txt" ]; then
    while IFS= read -r path; do
        # aox libraries this device does not need were removed above.
        [ -f "$MODPATH/$path" ] || continue
        case "$path" in
            system/vendor/odm/lib64/*.so|system/vendor/lib64/*.so|system/vendor/lib/*.so)
                chcon u:object_r:same_process_hal_file:s0 "$MODPATH/$path" ;;
        esac
    done < "$MODPATH/native-labels.txt"
fi
[ -f "$MODPATH/aox.sh" ] && aox_label
ui_print "Preparing camera filesystem (one-time installation step)."
# shellcheck source=module/mount-camera.sh
. "$MODPATH/mount-camera.sh"
if ! camera_prepare_image; then
    # Never leave installer mounts behind on failure.
    umount "$MODPATH/.camera-probe" 2>/dev/null
    umount "$MODPATH/.camera-image" 2>/dev/null
    cp "$MODPATH/aox.log" /data/local/tmp/ooscamera-install.log 2>/dev/null
    abort "Camera filesystem preparation failed; installation cancelled."
fi
ui_print "Ready. Reboot, open OOS Camera and grant its permissions."
if [ -f "$MODPATH/ksu-visibility" ]; then
    ui_print "Camera and launcher visibility will be configured automatically."
else
    ui_print "KernelSU App Profile: Camera -> Custom -> Umount modules OFF."
    ui_print "Leave camera Superuser access OFF."
fi
