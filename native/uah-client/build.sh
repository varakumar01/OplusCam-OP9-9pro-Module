#!/bin/sh
# Build liboplus-uah-client.so for arm64 Android without the NDK.
# Needs clang and ld.lld. The output's only DT_NEEDED entries are bionic's
# libc.so and libdl.so; link-time stubs carry those SONAMEs only.
# Usage: native/uah-client/build.sh OUTPUT.so
set -eu
out=${1:?usage: build.sh OUTPUT.so}
here=$(cd "$(dirname "$0")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
target=aarch64-linux-android30
cflags="--target=$target -O2 -fPIC -fvisibility=hidden -fno-stack-protector -fno-builtin
    -ffreestanding -fno-exceptions -fno-unwind-tables -fno-asynchronous-unwind-tables
    -Wall -Wextra -Werror"
# shellcheck disable=SC2086
clang $cflags -c "$here/uah_client.c" -o "$work/uah_client.o"

libc_symbols="free getuid malloc memcpy memset nanosleep pthread_create pthread_detach
    pthread_mutex_lock pthread_mutex_unlock strstr"
libdl_symbols="dlopen dlsym"
stub() {
    name=$1; shift
    : > "$work/$name.c"
    for symbol in "$@"; do echo "void $symbol(void) {}" >> "$work/$name.c"; done
    clang --target=$target -fPIC -fno-builtin -shared -nostdlib -fuse-ld=lld \
        -Wl,-soname,"$name" -o "$work/$name" "$work/$name.c"
}
# shellcheck disable=SC2086
stub libc.so $libc_symbols
# shellcheck disable=SC2086
stub libdl.so $libdl_symbols

# Every undefined reference must come from the stubbed bionic interface.
for symbol in $(llvm-nm -u "$work/uah_client.o" | awk '{print $NF}'); do
    # shellcheck disable=SC2086
    case " $(printf '%s ' $libc_symbols $libdl_symbols)" in
        *" $symbol "*) ;;
        *) echo "Unexpected undefined symbol: $symbol" >&2; exit 1 ;;
    esac
done

clang --target=$target -shared -nostdlib -fuse-ld=lld \
    -Wl,-soname,liboplus-uah-client.so -Wl,--hash-style=both -Wl,-z,max-page-size=16384 \
    -Wl,-z,relro -Wl,-z,now -Wl,--no-undefined-version -Wl,--build-id=none \
    -o "$out" "$work/uah_client.o" -L"$work" -lc -ldl
echo "$out"
