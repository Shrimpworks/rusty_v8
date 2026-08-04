#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
cache="$root/.governed-cache-arm64"
target="$root/target/governed-v150.2.0-linux-arm64"
out="$root/governed-out/v150.2.0/linux-arm64"
blocker_out="$root/governed-out/v150.2.0/linux-arm64-blocker"
gn="$cache/gn/gn"
ninja="$cache/ninja/ninja"
rust_toolchain="$cache/rust-toolchain"
cross="$cache/cross"
libclang="$cache/llvm19/usr/lib/llvm-19/lib"
llvm19_lib="$cache/llvm19/usr/lib/x86_64-linux-gnu"
cross_host_lib="$cross/usr/lib/x86_64-linux-gnu"
cross_linker="$cross/usr/bin/aarch64-linux-gnu-gcc-12"
linker="$root/scripts/governed/link_arm64.sh"
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
test -x "$cross_linker"
test -x "$linker"
test -x "$runner"
test -x "$cross/usr/bin/aarch64-linux-gnu-readelf"
test -e "$target_root/lib/ld-linux-aarch64.so.1"
test -f "$target_root/lib/libc.so.6"
test -f "$target_root/lib/libc_nonshared.a"
test -f "$target_include/features.h"
test -f "$target_include/features-time64.h"
test -f "$target_include/bits/wordsize.h"
test -e "$libclang/libclang-19.so.19"
test -e "$llvm19_lib/libLLVM.so.19.1"
test -e "$cross_host_lib/libbfd-2.40-arm64.so"
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
export LD_LIBRARY_PATH="$llvm19_lib:$cross_host_lib"
export RUSTY_V8_BINDGEN_RESOURCE_DIR="$libclang/clang/19"
export RUSTY_V8_GLIBC_SYSROOT="$target_root"
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
unset SCCACHE CCACHE RUSTC_WRAPPER BINDGEN_EXTRA_CLANG_ARGS

python3 scripts/governed/verify_arm64_inputs.py --require-submodules
build_log="$target/governed-build.log"
stage_status="$target/governed-stage.status"
test_binary_path="$target/fixed-test-binary.path"
readelf="$cross/usr/bin/aarch64-linux-gnu-readelf"

run_stage() {
  stage=$1
  log=$2
  shift 2
  printf '::group::governed arm64 stage: %s\n' "$stage"
  (
    set +e
    "$@"
    status=$?
    printf '%s\n' "$status" > "$stage_status"
    exit 0
  ) 2>&1 | tee "$log"
  status=$(cat "$stage_status")
  rm -f "$stage_status"
  printf 'governed-arm64-stage=%s exit-status=%s\n' "$stage" "$status"
  printf '::endgroup::\n'
  return "$status"
}

retain_failure() {
  stage=$1
  status=$2
  python3 scripts/governed/collect_arm64_blocker.py \
    --phase "$stage" \
    --exit-status "$status" \
    --output "$blocker_out"
  exit "$status"
}

identify_test_binary() {
  candidates="$target/fixed-test-binary-candidates.txt"
  find "$target/aarch64-unknown-linux-gnu/release/deps" \
    -maxdepth 1 -type f -name 'test_api-*' -perm -0100 -print | sort > "$candidates"
  count=$(wc -l < "$candidates" | tr -d ' ')
  printf 'candidate-count=%s\n' "$count"
  cat "$candidates"
  test "$count" -eq 1
  test_binary=$(sed -n '1p' "$candidates")
  test -n "$test_binary"
  printf '%s\n' "$test_binary" > "$test_binary_path"
  "$readelf" -h "$test_binary"
  "$readelf" -h "$test_binary" | grep -Eq 'Machine:[[:space:]]+AArch64'
}

identify_link_probe() {
  "$readelf" -h "$link_probe"
  "$readelf" -h "$link_probe" | grep -Eq 'Machine:[[:space:]]+AArch64'
}

link_probe="$target/arm64-link-probe"
link_probe_log="$target/arm64-link-probe.log"
if run_stage arm64-link-probe "$link_probe_log" \
  "$linker" scripts/governed/arm64_link_probe.c -o "$link_probe"; then
  :
else
  status=$?
  retain_failure arm64-link-probe "$status"
fi

link_probe_readelf_log="$target/arm64-link-probe-readelf.log"
if run_stage arm64-link-probe-readelf "$link_probe_readelf_log" identify_link_probe; then
  :
else
  status=$?
  retain_failure arm64-link-probe-readelf "$status"
fi

link_probe_qemu_log="$target/arm64-link-probe-qemu.log"
if run_stage arm64-link-probe-qemu "$link_probe_qemu_log" \
  "$runner" -L "$target_root" "$link_probe"; then
  :
else
  status=$?
  retain_failure arm64-link-probe-qemu "$status"
fi

if run_stage cargo-build "$build_log" \
  "$rust_toolchain/bin/cargo" build --frozen --release \
  --target aarch64-unknown-linux-gnu --features simdutf -j8; then
  :
else
  status=$?
  retain_failure cargo-build "$status"
fi

test_compile_log="$target/fixed-test-compile.log"
if run_stage fixed-test-compile "$test_compile_log" \
  "$rust_toolchain/bin/cargo" test --frozen --release \
  --target aarch64-unknown-linux-gnu --features simdutf \
  --test test_api --no-run -j8; then
  :
else
  status=$?
  retain_failure fixed-test-compile "$status"
fi

test_readelf_log="$target/fixed-test-readelf.log"
if run_stage fixed-test-readelf "$test_readelf_log" identify_test_binary; then
  :
else
  status=$?
  retain_failure fixed-test-readelf "$status"
fi

test_binary=$(cat "$test_binary_path")
verification="$target/fixed-verification.txt"
if run_stage fixed-test-qemu "$verification" \
  "$runner" -L "$target_root" "$test_binary" get_version --exact; then
  :
else
  status=$?
  retain_failure fixed-test-qemu "$status"
fi

collection_log="$target/evidence-collection.log"
if run_stage evidence-collection "$collection_log" \
  python3 scripts/governed/collect_arm64_evidence.py; then
  :
else
  status=$?
  retain_failure evidence-collection "$status"
fi

bundle_log="$target/bundle-verification.log"
if run_stage bundle-verification "$bundle_log" \
  python3 scripts/governed/verify_arm64_release.py \
  governed-out/v150.2.0/linux-arm64; then
  :
else
  status=$?
  retain_failure bundle-verification "$status"
fi
