#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
image="docker.io/library/rust@sha256:307d198027388f780db83929487de35084a73ecbaa31319989438db38103439f"
cache="$root/.governed-cache-arm64"
target="$root/target/governed-v150.2.0-linux-arm64"
out="$root/governed-out/v150.2.0/linux-arm64"
blocker_out="$root/governed-out/v150.2.0/linux-arm64-blocker"
mode=${1:-all}

case "$mode" in
  verify)
    exec python3 "$root/scripts/governed/verify_arm64_inputs.py" --require-submodules
    ;;
  prefetch|build|all) ;;
  *)
    echo "usage: $0 {verify|prefetch|build|all}" >&2
    exit 2
    ;;
esac

mkdir -p "$cache/home"
host_os=$(uname -s)
host_arch=$(uname -m)
host_kernel=$(uname -r)
docker_server_os=$(docker version --format '{{.Server.Os}}')
docker_server_arch=$(docker version --format '{{.Server.Arch}}')
docker_server_version=$(docker version --format '{{.Server.Version}}')
python3 -c 'import json,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(json.dumps({"schemaVersion":1,"profile":"linux-arm64-release-simdutf-v1","physicalHost":{"os":sys.argv[2],"architecture":sys.argv[3],"kernel":sys.argv[4]},"dockerServer":{"os":sys.argv[5],"architecture":sys.argv[6],"version":sys.argv[7]},"buildPlatform":"linux/amd64","targetPlatform":"linux/arm64","method":"cross","independentBuilder":False},indent=2,sort_keys=True)+"\n")' "$cache/host-environment.json" "$host_os" "$host_arch" "$host_kernel" "$docker_server_os" "$docker_server_arch" "$docker_server_version"

uid=$(id -u)
gid=$(id -g)
common="--rm --platform linux/amd64 --user $uid:$gid -e HOME=/workspace/.governed-cache-arm64/home -v $root:/workspace -w /workspace"

if [ "$mode" = prefetch ] || [ "$mode" = all ]; then
  # shellcheck disable=SC2086
  docker run $common "$image" python3 scripts/governed/prefetch_arm64.py
fi

if [ "$mode" = build ] || [ "$mode" = all ]; then
  case "$target" in "$root"/target/governed-v150.2.0-linux-arm64) ;; *) exit 1 ;; esac
  case "$out" in "$root"/governed-out/v150.2.0/linux-arm64) ;; *) exit 1 ;; esac
  case "$blocker_out" in "$root"/governed-out/v150.2.0/linux-arm64-blocker) ;; *) exit 1 ;; esac
  rm -rf "$target" "$out" "$blocker_out"
  # shellcheck disable=SC2086
  docker run $common --network none --cap-drop ALL --security-opt no-new-privileges \
    -e GOVERNED_NETWORK_MODE=none \
    -e GITHUB_RUN_ID="${GITHUB_RUN_ID:-local-unassigned}" \
    "$image" sh scripts/governed/build_arm64_offline.sh
fi
