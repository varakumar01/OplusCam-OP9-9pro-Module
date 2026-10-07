#!/system/bin/sh
MODDIR=${0%/*}
[ -x "$MODDIR/ksu-visibility" ] || exit 0
[ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
# Package ownership and default HOME are available after system boot.
while [ "$(getprop sys.boot_completed)" != 1 ]; do
    [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
    sleep 2
done
# Default HOME and owner-user package state must be usable on the first unlock.
while [ "$(am get-started-user-state 0 2>/dev/null | tail -n 1)" != RUNNING_UNLOCKED ]; do
    [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
    sleep 2
done
umask 077
CAMERA_VISIBILITY_TOOL="$MODDIR/ksu-visibility"
. "$MODDIR/visibility.sh"
exec > "$MODDIR/visibility.log" 2>&1
"$CAMERA_VISIBILITY_TOOL" check || exit 1
camera_attempt=0
while [ "$camera_attempt" -lt 30 ]; do
    [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || exit 0
    camera_home=$(cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME --user 0 2>/dev/null | tail -n 1)
    camera_home=${camera_home%%/*}
    camera_home_uid=$(camera_owner_uid "$camera_home")
    camera_app_uid=$(camera_owner_uid com.oplus.camera)
    case "$camera_home_uid:$camera_app_uid" in
        *[!0-9:]*|:*|*:) ;;
        *)
            if [ "$camera_home_uid" -ge 10000 ] && [ "$camera_home_uid" -lt 100000 ] &&
               [ "$camera_app_uid" -ge 10000 ] && [ "$camera_app_uid" -lt 100000 ]; then
                break
            fi
            ;;
    esac
    camera_attempt=$((camera_attempt + 1))
    sleep 2
done
[ "$camera_attempt" -lt 30 ] || { echo 'Package ownership unavailable after boot; no profile changes made.'; exit 1; }
echo "Boot ownership: launcher=$camera_home_uid camera=$camera_app_uid"
camera_enable_visibility "$camera_home" || exit 1
camera_enable_visibility com.oplus.camera || { camera_restore_visibility; exit 1; }
# Keep an independent executable for cleanup if the module is deleted.
cp "$CAMERA_VISIBILITY_TOOL" /data/adb/ooscamera-visibility/cleanup-tool || exit 1
chmod 0700 /data/adb/ooscamera-visibility/cleanup-tool || exit 1
CAMERA_VISIBILITY_TOOL=/data/adb/ooscamera-visibility/cleanup-tool
# Inotify observes disable/removal promptly without repeatedly running commands.
"$CAMERA_VISIBILITY_TOOL" watch "$MODDIR" || exit 1
camera_restore_visibility || exit 1
rm -f /data/adb/ooscamera-visibility/cleanup-tool
rmdir /data/adb/ooscamera-visibility 2>/dev/null
exit 0
