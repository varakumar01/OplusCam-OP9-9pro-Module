#!/system/bin/sh
MODDIR=${0%/*}
# shellcheck source=module/mount-camera.sh
. "$MODDIR/mount-camera.sh"
camera_mount || exit 1
if [ -f "$MODDIR/aox.sh" ]; then
    # shellcheck source=module/aox.sh
    . "$MODDIR/aox.sh"
    aox_mount_media
fi
# Live Photo working directories. The ROM trees create them from
# /odm/etc/init/init.camera_process.rc, which init reads before modules mount.
for dir in /data/vendor/camera_process /data/vendor/camera_process/livephoto; do
    [ -d "$dir" ] && continue
    mkdir "$dir" && chown camera:camera "$dir" && chmod 0777 "$dir" &&
        chcon --reference=/data/vendor/camera "$dir"
done
RESETPROP=/data/adb/ksu/bin/resetprop
[ -x "$RESETPROP" ] || RESETPROP=/data/adb/ksud
append_camera() {
    key=$1
    current=$(getprop "$key")
    case ",$current," in
        *,com.oplus.camera,*) return ;;
    esac
    value=${current:+$current,}com.oplus.camera
    if [ "$RESETPROP" = /data/adb/ksud ]; then
        "$RESETPROP" resetprop -n "$key" "$value"
    else
        "$RESETPROP" -n "$key" "$value"
    fi
}
append_camera persist.vendor.camera.privapp.list
append_camera persist.camera.privapp.list
# Preserve existing package entries. No persistent-property-store edits.
current=$(getprop vendor.camera.aux.packagelist)
[ -z "$current" ] || append_camera vendor.camera.aux.packagelist
