#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
cross="$root/.governed-cache-arm64/cross"
compiler="$cross/usr/bin/aarch64-linux-gnu-gcc-12"

test "$root" = /workspace
test "${GOVERNED_NETWORK_MODE:-}" = none
test -x "$compiler"
test -f "$cross/usr/aarch64-linux-gnu/lib/libc.so.6"
test -f "$cross/usr/aarch64-linux-gnu/lib/libc_nonshared.a"
test -f "$cross/usr/aarch64-linux-gnu/lib/ld-linux-aarch64.so.1"

exec "$compiler" "--sysroot=$cross" "$@"
