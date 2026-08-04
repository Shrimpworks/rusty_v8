#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
image="docker.io/library/rust@sha256:307d198027388f780db83929487de35084a73ecbaa31319989438db38103439f"
cache="$root/.governed-cache-arm64-gn-diagnostic"
target="$root/target/governed-v150.2.0-linux-arm64-gn-diagnostic"
out="$root/governed-out/v150.2.0/linux-arm64-gn-diagnostic"
mode=${1:-all}

case "$mode" in
  prefetch|diagnostic|all) ;;
  *)
    echo "usage: $0 {prefetch|diagnostic|all}" >&2
    exit 2
    ;;
esac

mkdir -p "$cache/home"
uid=$(id -u)
gid=$(id -g)
common="--rm --platform linux/amd64 --user $uid:$gid -e HOME=/workspace/.governed-cache-arm64-gn-diagnostic/home -v $root:/workspace -w /workspace"

if [ "$mode" = prefetch ] || [ "$mode" = all ]; then
  # shellcheck disable=SC2086
  docker run $common "$image" python3 scripts/governed/prefetch_arm64_gn_diagnostic.py
fi

if [ "$mode" = diagnostic ] || [ "$mode" = all ]; then
  case "$target" in "$root"/target/governed-v150.2.0-linux-arm64-gn-diagnostic) ;; *) exit 1 ;; esac
  case "$out" in "$root"/governed-out/v150.2.0/linux-arm64-gn-diagnostic) ;; *) exit 1 ;; esac
  rm -rf "$target" "$out"
  # shellcheck disable=SC2086
  docker run $common --network none --cap-drop ALL --security-opt no-new-privileges \
    -e GOVERNED_NETWORK_MODE=none \
    -e GITHUB_RUN_ID="${GITHUB_RUN_ID:-local-unassigned}" \
    -e GITHUB_SHA="${GITHUB_SHA:-local-unassigned}" \
    "$image" sh scripts/governed/diagnose_arm64_gn_offline.sh
fi
