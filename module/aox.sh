#!/system/bin/sh
# aox camera changes for ROMs that do not include them.
# Sourced by customize.sh (install) and post-fs-data.sh (media mount).
#
# Libraries listed in aox/files.txt were staged by build.py. Each one is
# kept only if its install rule matches this device and every DT_NEEDED
# library it lists can be found; otherwise the device copy stays.
# Text configuration edits (aox/edits.txt) are applied to the copy the
# module already ships, else to this device's own file. Edits that do not
# match are skipped and logged, never forced.

AOX_DIR=aox
# Device root; host tests point this at a fixture tree.
AOX_ROOT=${AOX_ROOT:-}

aox_log() {
    echo "$*" >> "$AOX_LOG"
}

# odm/... -> system/vendor/odm/..., vendor/... -> system/vendor/...
aox_staged() {
    case "$1" in
        odm/*) echo "$MODPATH/system/vendor/$1" ;;
        vendor/*) echo "$MODPATH/system/$1" ;;
    esac
}

aox_live() {
    echo "$AOX_ROOT/$1"
}

aox_sha256() {
    sha256sum "$1" 2>/dev/null | cut -d ' ' -f 1
}

# ---------------------------------------------------------------------------
# Edit primitives. Each prints the result to stdout and returns
#   0 changed, 1 already in the wanted state, 2 anchor/expected value missing.

# Set (or append) a VendorTag entry in an oplus_*_config JSON array.
# from: expected current value, or '*' for any value / append when missing.
aox_edit_tag() {
    awk -v tag="$2" -v type="$3" -v count="$4" -v from="$5" -v to="$6" '
        function quoted(line, key,    rest, p) {
            p = index(line, "\"" key "\"")
            if (!p) return ""
            rest = substr(line, p + length(key) + 2)
            if (!match(rest, /^[ \t]*:[ \t]*"/)) return ""
            rest = substr(rest, RLENGTH + 1)
            return substr(rest, 1, index(rest, "\"") - 1)
        }
        { line[++n] = $0 }
        END {
            for (i = 1; i <= n; i++) {
                if (quoted(line[i], "VendorTag") != tag) continue
                for (j = i + 1; j <= n && line[j] !~ /^[ \t]*}/; j++) {
                    if (!index(line[j], "\"Value\"")) continue
                    current = quoted(line[j], "Value")
                    if (current == to) exit 1
                    if (from != "*" && current != from) exit 2
                    p = index(line[j], "\"Value\"")
                    head = substr(line[j], 1, p + 6)
                    rest = substr(line[j], p + 7)
                    match(rest, /^[ \t]*:[ \t]*"/)
                    head = head substr(rest, 1, RLENGTH)
                    rest = substr(rest, RLENGTH + 1)
                    line[j] = head to substr(rest, index(rest, "\""))
                    for (k = 1; k <= n; k++) print line[k]
                    exit 0
                }
                exit 2
            }
            if (from != "*") exit 2
            # Append after the last object, before the closing bracket.
            for (k = n; k > 0 && line[k] !~ /^[ \t]*}[ \t\r]*$/; k--)
                if (line[k] !~ /^[ \t\r]*(\])?[ \t\r]*$/) exit 2
            if (k == 0) exit 2
            # Indent like the neighbouring (last) entry.
            indent = "  "
            for (i = k; i > 0; i--)
                if (match(line[i], /^[ \t]*"VendorTag"/)) {
                    indent = substr(line[i], 1, index(line[i], "\"") - 1)
                    break
                }
            cr = (line[k] ~ /\r$/) ? "\r" : ""
            for (i = 1; i < k; i++) print line[i]
            sub(/}/, "},", line[k])
            print line[k]
            print cr
            print "{" cr
            print indent "\"VendorTag\": \"" tag "\"," cr
            print indent "\"Type\": \"" type "\"," cr
            print indent "\"Count\": \"" count "\"," cr
            print indent "\"Value\": \"" to "\"" cr
            print "}" cr
            for (i = k + 1; i <= n; i++) print line[i]
            exit 0
        }' "$1"
}

# Set a key in an INI-style [Section]. from: expected current value, '*' for
# any existing value, '-' to also add the key when the section lacks it.
aox_edit_ini() {
    awk -v section="$2" -v key="$3" -v from="$4" -v to="$5" '
        function trim(s) { gsub(/^[ \t]+|[ \t\r]+$/, "", s); return s }
        { line[++n] = $0 }
        END {
            inside = 0; last = 0; found = 0
            for (i = 1; i <= n; i++) {
                if (line[i] ~ /^[ \t]*\[[^]]*\][ \t\r]*$/) {
                    if (inside) break
                    inside = (trim(line[i]) == "[" section "]")
                    if (inside) start = i
                    continue
                }
                if (!inside) continue
                if (trim(line[i]) != "" && line[i] !~ /^[ \t]*#/) last = i
                p = index(line[i], "=")
                if (p && trim(substr(line[i], 1, p - 1)) == key) { found = i; break }
            }
            if (!start) exit 2
            if (found) {
                p = index(line[found], "=")
                rest = substr(line[found], p + 1)
                current = trim(rest)
                if (current == to) exit 1
                if (from != "*" && from != "-" && current != from) exit 2
                match(rest, /^[ \t]*/)
                cr = (line[found] ~ /\r$/) ? "\r" : ""
                line[found] = substr(line[found], 1, p) substr(rest, 1, RLENGTH) to cr
                for (i = 1; i <= n; i++) print line[i]
                exit 0
            }
            if (from != "-") exit 2
            if (!last) last = start
            match(line[last], /^[ \t]*/)
            indent = (last == start) ? "    " : substr(line[last], 1, RLENGTH)
            cr = (line[last] ~ /\r$/) ? "\r" : ""
            for (i = 1; i <= last; i++) print line[i]
            print indent key " = " to cr
            for (i = last + 1; i <= n; i++) print line[i]
            exit 0
        }' "$1"
}

# Print an INI key value (trimmed) from a [Section].
aox_ini_get() {
    awk -v section="$2" -v key="$3" '
        function trim(s) { gsub(/^[ \t]+|[ \t\r]+$/, "", s); return s }
        /^[ \t]*\[[^]]*\][ \t\r]*$/ { inside = (trim($0) == "[" section "]"); next }
        inside && index($0, "=") {
            p = index($0, "=")
            if (trim(substr($0, 1, p - 1)) == key) { print trim(substr($0, p + 1)); exit }
        }' "$1"
}

# Set the first numeric "key" : N after a "mode" : "<mode>" line, before the
# next mode (oplus_camera_algo_switch_config).
aox_edit_modekey() {
    awk -v mode="$2" -v key="$3" -v from="$4" -v to="$5" '
        { line[++n] = $0 }
        END {
            armed = 0
            for (i = 1; i <= n; i++) {
                if (line[i] ~ /"mode"[ \t]*:/) {
                    armed = (index(line[i], "\"" mode "\"") > 0)
                    continue
                }
                if (!armed || !index(line[i], "\"" key "\"")) continue
                if (!match(line[i], /:[ \t]*-?[0-9]+/)) exit 2
                head = substr(line[i], 1, RSTART)
                value = substr(line[i], RSTART + 1, RLENGTH - 1)
                match(value, /^[ \t]*/)
                head = head substr(value, 1, RLENGTH)
                current = substr(value, RLENGTH + 1)
                if (current == to) exit 1
                if (from != "*" && current != from) exit 2
                match(line[i], /:[ \t]*-?[0-9]+/)
                line[i] = head to substr(line[i], RSTART + RLENGTH)
                for (k = 1; k <= n; k++) print line[k]
                exit 0
            }
            exit 2
        }' "$1"
}

# Replace one exact multi-line block (byte-exact, CRLF included).
aox_edit_block() {
    awk -v oldf="$2" -v newf="$3" '
        BEGIN {
            while ((getline l < oldf) > 0) o[++no] = l
            while ((getline l < newf) > 0) w[++nw] = l
        }
        function at(a, m, i,    k) {
            for (k = 1; k <= m; k++) if (t[i + k - 1] != a[k]) return 0
            return 1
        }
        { t[++nt] = $0 }
        END {
            for (i = 1; i + nw - 1 <= nt; i++) if (at(w, nw, i)) exit 1
            hit = 0
            for (i = 1; i + no - 1 <= nt; i++) if (at(o, no, i)) { if (hit) exit 2; hit = i }
            if (!hit) exit 2
            for (i = 1; i < hit; i++) print t[i]
            for (k = 1; k <= nw; k++) print w[k]
            for (i = hit + no; i <= nt; i++) print t[i]
            exit 0
        }' "$1"
}

# Raise maxBitRate inside <AudioEncoderCap name="NAME" ... /> to at least TO.
aox_edit_audio_cap() {
    awk -v name="$2" -v to="$3" '
        { line[++n] = $0 }
        END {
            inside = 0
            for (i = 1; i <= n; i++) {
                if (index(line[i], "<AudioEncoderCap") && index(line[i], "name=\"" name "\"")) inside = 1
                if (inside && match(line[i], /maxBitRate="[0-9]+"/)) {
                    current = substr(line[i], RSTART + 12, RLENGTH - 13) + 0
                    if (current >= to + 0) exit 1
                    line[i] = substr(line[i], 1, RSTART + 11) to substr(line[i], RSTART + RLENGTH - 1)
                    for (k = 1; k <= n; k++) print line[k]
                    exit 0
                }
                if (inside && index(line[i], "/>")) exit 2
            }
            exit 2
        }' "$1"
}

# ---------------------------------------------------------------------------
# Working copies.

# Prepare $AOX_WORK for a config path: the module's staged copy if any, else
# the device file. Returns 1 if neither exists.
aox_config_begin() {
    AOX_TARGET=$(aox_staged "$1")
    AOX_WORK="$MODPATH/$AOX_DIR/work/$1"
    [ -f "$AOX_WORK" ] && return 0
    mkdir -p "${AOX_WORK%/*}"
    if [ -f "$AOX_TARGET" ]; then
        cp -p "$AOX_TARGET" "$AOX_WORK"
    elif [ -f "$(aox_live "$1")" ]; then
        cp "$(aox_live "$1")" "$AOX_WORK"
    else
        return 1
    fi
}

# Run one edit primitive against the working copy of a config path.
aox_apply() {
    path=$1; label=$2; shift 2
    if ! aox_config_begin "$path"; then
        aox_log "skip  $label: /$path not on this device"
        return
    fi
    "$@" "$AOX_WORK" > "$AOX_WORK.new"
    case $? in
        0) mv "$AOX_WORK.new" "$AOX_WORK"; aox_log "apply $label" ;;
        1) rm -f "$AOX_WORK.new"; aox_log "ok    $label (already set)" ;;
        *) rm -f "$AOX_WORK.new"; aox_log "skip  $label: no matching entry on this device" ;;
    esac
}

aox_apply_edits() {
    while IFS='|' read -r op path a b c d e; do
        case "$op" in ''|'#'*) continue ;; esac
        case "$op" in
            tag)
                aox_apply "$path" "$path: $a=$e" \
                    aox_edit_tag_at "$a" "$b" "$c" "$d" "$e" ;;
            ini)
                aox_apply "$path" "$path: [$a] $b=$d" \
                    aox_edit_ini_at "$a" "$b" "$c" "$d" ;;
            zoommin)
                # [a] b's minimum zoom follows [a] c's minimum (the ultrawide ratio).
                if aox_config_begin "$path"; then
                    reference=$(aox_ini_get "$AOX_WORK" "$a" "$c")
                    current=$(aox_ini_get "$AOX_WORK" "$a" "$b")
                    if [ -n "$reference" ] && [ -n "$current" ] && [ "${current%%;*}" = "$d" ]; then
                        aox_apply "$path" "$path: [$a] $b min=${reference%%;*}" \
                            aox_edit_ini_at "$a" "$b" "$current" "${reference%%;*};${current#*;}"
                    elif [ -n "$current" ] && [ "${current%%;*}" = "${reference%%;*}" ]; then
                        aox_log "ok    $path: [$a] $b min (already set)"
                    else
                        aox_log "skip  $path: [$a] $b min: no matching entry on this device"
                    fi
                else
                    aox_log "skip  $path: [$a] $b min: /$path not on this device"
                fi ;;
            modekey)
                aox_apply "$path" "$path: $a/$b=$d" \
                    aox_edit_modekey_at "$a" "$b" "$c" "$d" ;;
            block)
                aox_apply_blocks "$path" "$a" ;;
            audiocap)
                aox_apply_media "$path" "$a" "$b" ;;
            *)
                aox_log "skip  unknown edit $op" ;;
        esac
    done < "$MODPATH/$AOX_DIR/edits.txt"
}

# Primitive wrappers for aox_apply: the working copy is the last argument.
aox_edit_tag_at() { aox_edit_tag "$6" "$1" "$2" "$3" "$4" "$5"; }
aox_edit_ini_at() { aox_edit_ini "$5" "$1" "$2" "$3" "$4"; }
aox_edit_modekey_at() { aox_edit_modekey "$5" "$1" "$2" "$3" "$4"; }

# A comma-separated group of blocks is applied together or not at all.
aox_apply_blocks() {
    path=$1; ids=$2
    if ! aox_config_begin "$path"; then
        aox_log "skip  $path: $ids: /$path not on this device"
        return
    fi
    cp "$AOX_WORK" "$AOX_WORK.group"
    state=ok
    for id in $(echo "$ids" | tr ',' ' '); do
        blocks="$MODPATH/$AOX_DIR/blocks/$id"
        aox_edit_block "$AOX_WORK.group" "$blocks.old" "$blocks.new" > "$AOX_WORK.new"
        case $? in
            0) mv "$AOX_WORK.new" "$AOX_WORK.group"; [ "$state" = skip ] || state=apply ;;
            1) rm -f "$AOX_WORK.new" ;;
            *) rm -f "$AOX_WORK.new"; state=skip ;;
        esac
    done
    case $state in
        apply) mv "$AOX_WORK.group" "$AOX_WORK"; aox_log "apply $path: $ids" ;;
        ok) rm -f "$AOX_WORK.group"; aox_log "ok    $path: $ids (already set)" ;;
        *) rm -f "$AOX_WORK.group"; aox_log "skip  $path: $ids: does not match this device" ;;
    esac
}

# Media profiles are single files outside the camera overlays: patch every
# variant this device has and bind-mount the result in post-fs-data.
aox_apply_media() {
    name=$2; to=$3
    for live in /vendor/etc/media_profiles_vendor.xml /vendor/etc/media_profiles_V1_0.xml \
            /vendor/etc/media_profiles.xml /odm/etc/media_profiles_vendor.xml; do
        [ -f "$AOX_ROOT$live" ] || continue
        staged="$MODPATH/$AOX_DIR/media$live"
        mkdir -p "${staged%/*}"
        aox_edit_audio_cap "$AOX_ROOT$live" "$name" "$to" > "$staged.new"
        case $? in
            0) mv "$staged.new" "$staged"; aox_log "apply $live: $name maxBitRate=$to" ;;
            1) rm -f "$staged.new"; aox_log "ok    $live: $name maxBitRate (already >= $to)" ;;
            *) rm -f "$staged.new"; aox_log "skip  $live: no $name encoder cap" ;;
        esac
    done
    rmdir -p "$MODPATH/$AOX_DIR/media/vendor/etc" "$MODPATH/$AOX_DIR/media/odm/etc" 2>/dev/null
}

# Move edited working copies into the staged payload when they differ from
# what the camera would otherwise read.
aox_commit_configs() {
    work="$MODPATH/$AOX_DIR/work"
    [ -d "$work" ] || return 0
    find "$work" -type f ! -name '*.new' ! -name '*.group' | while IFS= read -r copy; do
        path=${copy#"$work/"}
        target=$(aox_staged "$path")
        reference=$target
        [ -f "$reference" ] || reference=$(aox_live "$path")
        if ! cmp -s "$copy" "$reference"; then
            mkdir -p "${target%/*}"
            cat "$copy" > "$target"
            echo "$path" >> "$MODPATH/$AOX_DIR/configs.txt"
        fi
    done
    rm -rf "$work"
}

# ---------------------------------------------------------------------------
# Libraries.

aox_lib_dirs() {
    case "$1" in
        */lib64/*) abi=lib64 ;;
        *) abi=lib ;;
    esac
    echo "$MODPATH/system/vendor/odm/$abi $MODPATH/system/vendor/$abi $MODPATH/system/system_ext/$abi"
    for dir in /odm/$abi /vendor/$abi /vendor/$abi/egl /system/$abi /system_ext/$abi /product/$abi; do
        echo "$AOX_ROOT$dir"
    done
    for apex in "$AOX_ROOT/apex/com.android.runtime/$abi/bionic" "$AOX_ROOT"/apex/*/"$abi"; do
        [ -d "$apex" ] && echo "$apex"
    done
}

aox_have_lib() {
    for dir in $(aox_lib_dirs "$2"); do
        [ -f "$dir/$1" ] && return 0
    done
    return 1
}

# files.txt: path|rule|sha256|replace sha256s (comma)|needed (comma)
aox_select_libraries() {
    list="$MODPATH/$AOX_DIR/files.txt"
    [ -f "$list" ] || return 0
    : > "$MODPATH/$AOX_DIR/installed.txt"
    while IFS='|' read -r path rule digest replace needed; do
        case "$path" in ''|'#'*) continue ;; esac
        staged=$(aox_staged "$path")
        [ -f "$staged" ] || continue
        live=$(aox_live "$path")
        current=
        [ -f "$live" ] && current=$(aox_sha256 "$live")
        keep=0
        if [ "$current" = "$digest" ]; then
            reason="device already has this version"
        else
            case "$rule" in
                add)
                    if [ -z "$current" ]; then keep=1; else reason="device has its own copy"; fi ;;
                add-or-replace|replace)
                    if [ -z "$current" ] && [ "$rule" = add-or-replace ]; then
                        keep=1
                    elif [ -n "$current" ] && case ",$replace," in *",$current,"*) true ;; *) false ;; esac; then
                        keep=1
                    elif [ -z "$current" ]; then
                        reason="not present on this device"
                    else
                        reason="device copy differs from the version this change was made for"
                    fi ;;
                uah)
                    # Never replace a stock OEM client (it links the urcc/uah cores).
                    if [ -z "$current" ] || ! grep -qE 'libuahcore|liburcccore' "$live"; then
                        keep=1
                    else
                        reason="device has the stock OEM client"
                    fi ;;
                *) reason="unknown rule $rule" ;;
            esac
        fi
        if [ "$keep" = 1 ]; then
            echo "$path|$needed" >> "$MODPATH/$AOX_DIR/installed.txt"
        else
            rm -f "$staged"
            aox_log "skip  /$path: $reason"
        fi
    done < "$list"
    # Drop libraries whose dependencies are missing, until nothing changes.
    changed=1
    while [ "$changed" = 1 ]; do
        changed=0
        : > "$MODPATH/$AOX_DIR/installed.next"
        while IFS='|' read -r path needed; do
            missing=
            for lib in $(echo "$needed" | tr ',' ' '); do
                aox_have_lib "$lib" "$path" || { missing=$lib; break; }
            done
            if [ -n "$missing" ]; then
                rm -f "$(aox_staged "$path")"
                aox_log "skip  /$path: needs $missing, not on this device"
                changed=1
            else
                echo "$path|$needed" >> "$MODPATH/$AOX_DIR/installed.next"
            fi
        done < "$MODPATH/$AOX_DIR/installed.txt"
        mv "$MODPATH/$AOX_DIR/installed.next" "$MODPATH/$AOX_DIR/installed.txt"
    done
    while IFS='|' read -r path needed; do
        aox_log "add   /$path"
    done < "$MODPATH/$AOX_DIR/installed.txt"
}

# ---------------------------------------------------------------------------
# Entry points.

aox_install() {
    [ -d "$MODPATH/$AOX_DIR" ] || return 0
    AOX_LOG="$MODPATH/aox.log"
    : > "$AOX_LOG"
    ui_print "Applying aox camera changes where this ROM lacks them."
    aox_select_libraries
    aox_apply_edits
    aox_commit_configs
    # The adsp overlay is mounted only when it carries a file.
    rmdir -p "$MODPATH/system/vendor/odm/lib/rfsa/adsp" 2>/dev/null
    applied=$(grep -c '^apply\|^add' "$AOX_LOG")
    ui_print "aox: $applied change(s) applied; details in aox.log."
}

# Give staged replacements the device file's SELinux label (after the
# installer's blanket system_file labelling).
aox_label() {
    [ -d "$MODPATH/$AOX_DIR" ] || return 0
    for list in configs.txt installed.txt; do
        [ -f "$MODPATH/$AOX_DIR/$list" ] || continue
        while IFS='|' read -r path rest; do
            staged=$(aox_staged "$path")
            live=$(aox_live "$path")
            [ -f "$staged" ] || continue
            case "$path" in
                */lib/rfsa/adsp/*|*/etc/*)
                    [ -f "$live" ] && chcon --reference="$live" "$staged" ;;
            esac
        done < "$MODPATH/$AOX_DIR/$list"
    done
    if [ -d "$MODPATH/$AOX_DIR/media" ]; then
        find "$MODPATH/$AOX_DIR/media" -type f | while IFS= read -r staged; do
            live=$AOX_ROOT${staged#"$MODPATH/$AOX_DIR/media"}
            chmod 0644 "$staged"
            chcon --reference="$live" "$staged"
        done
    fi
}

# post-fs-data: bind the patched media profiles over the device files.
aox_mount_media() {
    media="$MODDIR/$AOX_DIR/media"
    [ -d "$media" ] || return 0
    find "$media" -type f | while IFS= read -r source; do
        target=${source#"$media"}
        if [ -f "$target" ] && mount -o bind "$source" "$target" >> "$MODDIR/mount.log" 2>&1; then
            echo "Mounted $target" >> "$MODDIR/mount.log"
        else
            echo "Failed $target; media profile unchanged." >> "$MODDIR/mount.log"
        fi
    done
}
