#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
cache="$root/.governed-cache-arm64"
target="$root/target/governed-v150.2.0-linux-arm64"
out="$root/governed-out/v150.2.0/linux-arm64"
gn="$cache/gn/gn"
ninja="$cache/ninja/ninja"
rust_toolchain="$cache/rust-toolchain"
cross="$cache/cross"
libclang="$cache/llvm19/usr/lib/llvm-19/lib"
llvm19_lib="$cache/llvm19/usr/lib/x86_64-linux-gnu"
linker="$cross/usr/bin/aarch64-linux-gnu-gcc-12"
runner="$cross/usr/bin/qemu-aarch64-static"
target_root="$cross/usr/aarch64-linux-gnu"
target_include="$target_root/include"

test "$(pwd)" = /workspace
test "${GOVERNED_NETWORK_MODE:-}" = none
test ! -e "$target"
test ! -e "$out"
test ! -e "$cache/sccache"
test ! -e "$cache/ccache"
if command -v sccache >/dev/null 2>&1 || command -v ccache >/dev/null 2>&1; then
  echo "compiler object cache executable is forbidden for the clean arm64 build" >&2
  exit 1
fi
if awk 'NR > 1 && $2 == "00000000" { found=1 } END { exit found ? 0 : 1 }' /proc/net/route; then
  echo "default network route exists in the network-disabled arm64 build" >&2
  exit 1
fi

test -x "$gn"
test -x "$ninja"
test -x "$cache/clang/bin/clang"
test -x "$rust_toolchain/bin/rustc"
test -x "$rust_toolchain/bin/cargo"
test -x "$linker"
test -x "$runner"
test -x "$cross/usr/bin/aarch64-linux-gnu-readelf"
test -e "$target_root/lib/ld-linux-aarch64.so.1"
test -f "$target_include/features.h"
test -f "$target_include/features-time64.h"
test -f "$target_include/bits/wordsize.h"
test -e "$libclang/libclang-19.so.19"
test -e "$llvm19_lib/libLLVM.so.19.1"
test -d "$libclang/clang/19/include"
test -d "$rust_toolchain/lib/rustlib/aarch64-unknown-linux-gnu/lib"
test -f "$cache/prefetch-evidence.json"
test -f "$cache/host-environment.json"

route_sha=$(sha256sum /proc/net/route | awk '{print $1}')
export CLEAN_ROUTE_SHA="$route_sha"
python3 -c 'import json,os,pathlib; pathlib.Path("/workspace/.governed-cache-arm64/clean-cache-proof.json").write_text(json.dumps({"schemaVersion":1,"profile":"linux-arm64-release-simdutf-v1","networkMode":os.environ["GOVERNED_NETWORK_MODE"],"procNetRouteSha256":os.environ["CLEAN_ROUTE_SHA"],"targetDirectoryExisted":False,"outputDirectoryExisted":False,"sccachePresent":False,"ccachePresent":False},indent=2,sort_keys=True)+"\n")'

mkdir -p "$target"
export PATH="$rust_toolchain/bin:$cross/usr/bin:$PATH"
export CARGO_HOME="$cache/cargo-home"
export CARGO_TARGET_DIR="$target"
export CARGO_NET_OFFLINE=true
export RUSTC="$rust_toolchain/bin/rustc"
export CLANG_BASE_PATH="$cache/clang"
export LIBCLANG_PATH="$libclang"
export LD_LIBRARY_PATH="$llvm19_lib"
export BINDGEN_EXTRA_CLANG_ARGS="--target=aarch64-linux-gnu -isystem$target_include -resource-dir=$libclang/clang/19"
export GN="$gn"
export NINJA="$ninja"
export V8_FROM_SOURCE=1
export PRINT_GN_ARGS=1
export SOURCE_DATE_EPOCH=1784209467
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
export NUM_JOBS=8
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER="$linker"
export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_RUNNER="$runner -L $target_root"
unset SCCACHE CCACHE RUSTC_WRAPPER

python3 scripts/governed/verify_arm64_inputs.py --require-submodules
build_log="$target/governed-build.log"
build_status="$target/governed-build.status"
(
  set +e
  "$rust_toolchain/bin/cargo" build --frozen --release --target aarch64-unknown-linux-gnu --features simdutf -j8
  status=$?
  printf '%s\n' "$status" > "$build_status"
  exit 0
) 2>&1 | tee "$build_log"
status=$(cat "$build_status")
rm -f "$build_status"
if [ "$status" -ne 0 ]; then
  exit "$status"
fi
"$rust_toolchain/bin/cargo" test --frozen --release --target aarch64-unknown-linux-gnu --features simdutf --test test_api get_version -- --exact > "$target/fixed-verification.txt" 2>&1
cat "$target/fixed-verification.txt"
python3 scripts/governed/collect_arm64_evidence.py
python3 scripts/governed/verify_arm64_release.py governed-out/v150.2.0/linux-arm64
