#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
image="docker.io/library/rust@sha256:307d198027388f780db83929487de35084a73ecbaa31319989438db38103439f"
mode=${1:-all}

case "$mode" in
  verify)
    exec python3 "$root/scripts/governed/verify_inputs.py" --require-submodules
    ;;
  prefetch|build|all) ;;
  *)
    echo "usage: $0 {verify|prefetch|build|all}" >&2
    exit 2
    ;;
esac

mkdir -p "$root/.governed-cache/home" "$root/target" "$root/governed-out"
uid=$(id -u)
gid=$(id -g)
common="--rm --platform linux/amd64 --user $uid:$gid -e HOME=/workspace/.governed-cache/home -v $root:/workspace -w /workspace"

if [ "$mode" = prefetch ] || [ "$mode" = all ]; then
  # shellcheck disable=SC2086
  docker run $common "$image" python3 scripts/governed/prefetch.py
fi

if [ "$mode" = build ] || [ "$mode" = all ]; then
  # shellcheck disable=SC2086
  docker run $common --network none --cap-drop ALL --security-opt no-new-privileges \
    -e GITHUB_RUN_ID="${GITHUB_RUN_ID:-local-unassigned}" \
    "$image" sh scripts/governed/build-offline.sh
fi
