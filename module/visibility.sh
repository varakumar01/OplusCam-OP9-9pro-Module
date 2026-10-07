#!/system/bin/sh
# Sourced by candidate-only lifecycle scripts. No global KernelSU defaults.
camera_owner_uid() {
    cmd package list packages -U --user 0 2>/dev/null |
        awk -v target="package:$1" '$1 == target { sub(/^uid:/, "", $2); gsub(/\r/, "", $2); print $2 }'
}

camera_restore_visibility() {
    for camera_state in /data/adb/ooscamera-visibility/*.state; do
        [ -f "$camera_state" ] || continue
        camera_package=${camera_state##*/}
        camera_package=${camera_package%.state}
        camera_uid=$(camera_owner_uid "$camera_package")
        # Package removal/replacement must never restore a policy to another UID.
        [ -n "$camera_uid" ] || continue
        "$CAMERA_VISIBILITY_TOOL" restore "$camera_package" "$camera_uid" || return 1
    done
}

camera_enable_visibility() {
    camera_uid=$(camera_owner_uid "$1")
    case "$camera_uid" in
        ''|*[!0-9]*) echo "Package ownership is not ready for $1"; return 1 ;;
    esac
    echo "Configuring owner-user visibility: $1 UID $camera_uid"
    camera_result=$("$CAMERA_VISIBILITY_TOOL" apply "$1" "$camera_uid") || return 1
    echo "$camera_result"
    case "$camera_result" in
        'Mount visibility enabled;'*)
            # A pre-existing process retains its old mount namespace.
            camera_foreground=$(dumpsys activity activities 2>/dev/null | sed -n '/topResumedActivity=/p')
            am force-stop --user 0 "$1" >/dev/null 2>&1 || return 1
            case "$camera_foreground" in
                *" $1/"*)
                    if [ "$1" = com.oplus.camera ]; then
                        am start --user 0 -n com.oplus.camera/com.oplus.camera.Camera >/dev/null 2>&1
                    else
                        am start --user 0 -a android.intent.action.MAIN -c android.intent.category.HOME -p "$1" >/dev/null 2>&1
                    fi
                    ;;
            esac
            if [ "$1" = com.oplus.camera ]; then
                # Both states stay enabled; trigger launcher icon/label refresh.
                camera_enabled=$(dumpsys package com.oplus.camera 2>/dev/null |
                    sed -n 's/.*User 0:.* enabled=\([0-9]*\).*/\1/p')
                case "$camera_enabled" in
                    0) pm enable --user 0 com.oplus.camera >/dev/null 2>&1 && pm default-state --user 0 com.oplus.camera >/dev/null 2>&1 ;;
                    1) pm default-state --user 0 com.oplus.camera >/dev/null 2>&1 && pm enable --user 0 com.oplus.camera >/dev/null 2>&1 ;;
                    *) : ;; # Respect a deliberately disabled app.
                esac
            fi
            ;;
    esac
}
