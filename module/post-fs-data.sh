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
# cameraserver, when the installer kept it. It has to sit on a mount without
# nosuid, or init may not enter the cameraserver domain when it starts it.
if [ -f "$MODDIR/aox/cameraserver" ]; then
    SRV=/dev/ooscamera-bin
    mkdir -p "$SRV" && mount -t tmpfs -o mode=755 tmpfs "$SRV" &&
        cp "$MODDIR/aox/cameraserver" "$SRV/cameraserver" &&
        chown root:shell "$SRV/cameraserver" && chmod 755 "$SRV/cameraserver" &&
        chcon u:object_r:cameraserver_exec:s0 "$SRV/cameraserver" &&
        mount -o bind "$SRV/cameraserver" /system/bin/cameraserver ||
        echo "cameraserver not mounted" >> "$MODDIR/mount.log"
fi
# Live Photo working directories. The ROM trees create them from
# /odm/etc/init/init.camera_process.rc, which init reads before modules mount.
for dir in /data/vendor/camera_process /data/vendor/camera_process/livephoto; do
    [ -d "$dir" ] && continue
    mkdir "$dir" && chown camera:camera "$dir" && chmod 0777 "$dir"
done
# A ROM without the aox policy leaves the store as vendor_data_file, which
# the app may not write. Use the type sepolicy.rule declares, else the camera
# data label.
chcon -R u:object_r:vendor_oplus_camera_process_file:s0 /data/vendor/camera_process 2>/dev/null ||
    chcon -R --reference=/data/vendor/camera /data/vendor/camera_process
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
