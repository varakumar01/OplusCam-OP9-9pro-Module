#!/system/bin/sh
# Camera-only read-only overlays. Sourced by the installer and boot script.
# Uses KernelSU's bundled BusyBox; no metamodule or writable system partition.
camera_mounts() {
    cat <<'EOF'
etc/sysconfig /system/etc/sysconfig
framework /system/framework
system_ext/etc/default-permissions /system_ext/etc/default-permissions
system_ext/etc/permissions /system_ext/etc/permissions
system_ext/framework /system_ext/framework
system_ext/lib64 /system_ext/lib64
system_ext/priv-app /system_ext/priv-app
vendor/lib64 /vendor/lib64
vendor/odm/etc/camera /odm/etc/camera
vendor/odm/lib64 /odm/lib64
EOF
    # Candidate-only ARMv7 graphics payload. Release images keep ten overlays.
    if [ -d "$1/vendor/lib" ]; then
        echo 'vendor/lib /vendor/lib'
    fi
    # aox-cam4 ArcSoft HVX skels, only when this device takes them.
    if [ -d "$1/vendor/odm/lib/rfsa/adsp" ]; then
        echo 'vendor/odm/lib/rfsa/adsp /odm/lib/rfsa/adsp'
    fi
}

camera_prepare_image() {
    image="$MODPATH/camera.img"
    stage="$MODPATH/.camera-image"
    # Leave room for filesystem metadata and future small payload additions.
    payload_kib=$(du -sk "$MODPATH/system" | awk '{print $1}')
    image_kib=$(( (payload_kib + 131072 + 65535) / 65536 * 65536 ))
    free_kib=$(df -Pk "$MODPATH" | tail -n 1 | awk '{print $4}')
    if [ "$free_kib" -lt "$((image_kib + 65536))" ]; then
        echo 'Insufficient free storage to prepare the camera filesystem.'
        return 1
    fi
    dd if=/dev/zero of="$image" bs=1024 count=0 seek="$image_kib" || return 1
    /system/bin/mkfs.ext4 -q -O ^has_journal -m 0 -L OOSCamera "$image" || return 1
    chmod 0600 "$image"
    chcon u:object_r:ksu_file:s0 "$image" || return 1
    mkdir -p "$stage" || return 1
    mount -t ext4 -o loop,rw,nodev,nosuid,noatime "$image" "$stage" || return 1
    camera_image_ok=1
    cp -aL "$MODPATH/system/." "$stage/" || camera_image_ok=0
    # BusyBox cp does not reliably preserve security.selinux on this device.
    while IFS= read -r source; do
        relative=${source#"$MODPATH/system"}
        chcon --reference="$source" "$stage$relative" || camera_image_ok=0
    done <<EOF
$(find -L "$MODPATH/system")
EOF
    # Validate each overlay against the current kernel before accepting install.
    mkdir -p "$MODPATH/.camera-probe" || camera_image_ok=0
    while read -r relative target; do
        [ -d "$stage/$relative" ] && [ -d "$target" ] || { camera_image_ok=0; break; }
        if mount -t overlay -o "ro,lowerdir=$stage/$relative:$target" KSU "$MODPATH/.camera-probe"; then
            umount "$MODPATH/.camera-probe" || { camera_image_ok=0; break; }
        else
            camera_image_ok=0
            break
        fi
    done <<EOF
$(camera_mounts "$stage")
EOF
    sync
    umount "$stage" || return 1
    rmdir "$stage" "$MODPATH/.camera-probe" || return 1
    [ "$camera_image_ok" = 1 ] || return 1
    # The image now owns the payload: avoid storing a second unpacked copy.
    rm -rf "$MODPATH/system"
}

camera_mount() {
    [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || return 1
    [ ! -f /dev/ooscamera-mounted ] || return 0
    : > "$MODDIR/mount.log"
    if [ -f "$MODDIR/boot-pending" ]; then
        echo 'Previous boot did not complete; camera module disabled for recovery.' >> "$MODDIR/mount.log"
        touch "$MODDIR/disable"
        return 1
    fi
    touch "$MODDIR/boot-pending" || return 1
    stage=/mnt/ooscamera
    camera_mounted=
    mkdir -p "$stage" || return 1
    # KernelSU restores module labels before post-fs-data; loop access needs this.
    chcon u:object_r:ksu_file:s0 "$MODDIR/camera.img" || return 1
    if ! mount -t ext4 -o loop,ro,nodev,nosuid,noatime "$MODDIR/camera.img" "$stage" >> "$MODDIR/mount.log" 2>&1; then
        echo 'Cannot mount camera image; no camera overlays applied.' >> "$MODDIR/mount.log"
        touch "$MODDIR/disable"
        return 1
    fi
    camera_mount_ok=1
    while read -r relative target; do
        if [ -d "$stage/$relative" ] && [ -d "$target" ] &&
            mount -t overlay -o "ro,lowerdir=$stage/$relative:$target" KSU "$target" >> "$MODDIR/mount.log" 2>&1; then
            camera_mounted="$target $camera_mounted"
            echo "Mounted $target" >> "$MODDIR/mount.log"
        else
            camera_mount_ok=0
            echo "Failed $target; rolling back camera overlays." >> "$MODDIR/mount.log"
            break
        fi
    done <<EOF
$(camera_mounts "$stage")
EOF
    if [ "$camera_mount_ok" != 1 ]; then
        for target in $camera_mounted; do
            umount "$target" >> "$MODDIR/mount.log" 2>&1
        done
        umount "$stage" >> "$MODDIR/mount.log" 2>&1
        touch "$MODDIR/disable"
        return 1
    fi
    touch /dev/ooscamera-mounted
    echo 'Camera overlays ready.' >> "$MODDIR/mount.log"
}
