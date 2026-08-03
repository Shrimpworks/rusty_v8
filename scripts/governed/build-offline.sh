#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cache="$root/.governed-cache"
target="$root/target/governed-v150.2.0"
gn="$cache/gn/gn"
ninja="$cache/ninja/ninja"
libclang="$root/third_party/rust-toolchain/lib"

test "$(pwd)" = /workspace
test -x "$gn"
test -x "$ninja"
test -x "$cache/clang/bin/clang"
test -e "$libclang/libclang.so"
test -f "$cache/prefetch-evidence.json"

export CARGO_HOME="$cache/cargo-home"
export CARGO_TARGET_DIR="$target"
export CARGO_NET_OFFLINE=true
export RUSTUP_TOOLCHAIN=1.91.0-x86_64-unknown-linux-gnu
export CLANG_BASE_PATH="$cache/clang"
export LIBCLANG_PATH="$libclang"
export BINDGEN_EXTRA_CLANG_ARGS="-resource-dir=$cache/clang/lib/clang/23"
export GN="$gn"
export NINJA="$ninja"
export V8_FROM_SOURCE=1
export PRINT_GN_ARGS=1
export SOURCE_DATE_EPOCH=1784209467
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export TZ=UTC
export NUM_JOBS=8

python3 scripts/governed/verify_inputs.py --require-submodules
cargo build --frozen --release --target x86_64-unknown-linux-gnu --features simdutf -j8
cargo test --frozen --release --target x86_64-unknown-linux-gnu --features simdutf --test test_api get_version -- --exact \
  > "$target/fixed-verification.txt" 2>&1
python3 scripts/governed/collect_evidence.py
python3 scripts/governed/verify_release.py governed-out/v150.2.0
