#!/system/bin/sh
MODDIR=${0%/*}
CAMERA_VISIBILITY_TOOL="$MODDIR/ksu-visibility"
[ -x "$CAMERA_VISIBILITY_TOOL" ] || exit 0
. "$MODDIR/visibility.sh"
camera_restore_visibility
# Nothing left to restore: the helper's lock file and directory can go.
ls /data/adb/ooscamera-visibility/*.state >/dev/null 2>&1 ||
    rm -rf /data/adb/ooscamera-visibility
