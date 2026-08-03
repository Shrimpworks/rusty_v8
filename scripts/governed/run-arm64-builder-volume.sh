#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
image="docker.io/library/rust@sha256:307d198027388f780db83929487de35084a73ecbaa31319989438db38103439f"
head=$(git -C "$root" rev-parse HEAD)
short_head=$(printf '%s' "$head" | cut -c1-12)
volume="rusty-v8-governed-arm64-$short_head"
carrier="rusty-v8-governed-arm64-carrier-$short_head"
uid=$(id -u)
gid=$(id -g)
mode=${1:-all}

common="--rm --platform linux/amd64 --user $uid:$gid -e HOME=/workspace/.governed-cache-arm64/home -v $volume:/workspace -w /workspace"

volume_exists() {
  docker volume inspect "$volume" >/dev/null 2>&1
}

carrier_exists() {
  docker container inspect "$carrier" >/dev/null 2>&1
}

seed() {
  if ! git -C "$root" diff --quiet || ! git -C "$root" diff --cached --quiet || [ -n "$(git -C "$root" status --porcelain)" ]; then
    echo "refusing to seed a governed builder from a dirty integration checkout" >&2
    exit 1
  fi
  if volume_exists || carrier_exists; then
    echo "refusing to reuse existing governed builder state: $volume or $carrier" >&2
    exit 1
  fi
  docker volume create "$volume" >/dev/null
  docker create --name "$carrier" --platform linux/amd64 -v "$volume:/workspace" "$image" true >/dev/null
  docker cp "$root/." "$carrier:/workspace"
  docker run --rm --platform linux/amd64 -v "$volume:/workspace" "$image" chown -R "$uid:$gid" /workspace
  host_os=$(uname -s)
  host_arch=$(uname -m)
  host_kernel=$(uname -r)
  docker_server_os=$(docker version --format '{{.Server.Os}}')
  docker_server_arch=$(docker version --format '{{.Server.Arch}}')
  docker_server_version=$(docker version --format '{{.Server.Version}}')
  # shellcheck disable=SC2086
  docker run $common "$image" python3 -c 'import json,pathlib,sys; p=pathlib.Path("/workspace/.governed-cache-arm64"); p.mkdir(exist_ok=True); (p/"home").mkdir(exist_ok=True); (p/"host-environment.json").write_text(json.dumps({"schemaVersion":1,"profile":"linux-arm64-release-simdutf-v1","physicalHost":{"os":sys.argv[1],"architecture":sys.argv[2],"kernel":sys.argv[3]},"dockerServer":{"os":sys.argv[4],"architecture":sys.argv[5],"version":sys.argv[6]},"buildPlatform":"linux/amd64","targetPlatform":"linux/arm64","method":"cross","workspaceTransport":"isolated-docker-volume","independentBuilder":False},indent=2,sort_keys=True)+"\n")' "$host_os" "$host_arch" "$host_kernel" "$docker_server_os" "$docker_server_arch" "$docker_server_version"
  # shellcheck disable=SC2086
  docker run $common --network none "$image" sh -c 'test "$(git rev-parse HEAD)" = '"$head"' && test -z "$(git status --porcelain)" && python3 scripts/governed/verify_arm64_inputs.py --require-submodules'
  echo "seeded clean isolated builder volume $volume at $head"
}

prefetch() {
  volume_exists || { echo "missing seeded volume: $volume" >&2; exit 1; }
  # shellcheck disable=SC2086
  docker run $common "$image" python3 scripts/governed/prefetch_arm64.py
}

build() {
  volume_exists || { echo "missing prefetched volume: $volume" >&2; exit 1; }
  # shellcheck disable=SC2086
  docker run $common "$image" sh -c 'rm -rf /workspace/target/governed-v150.2.0-linux-arm64 /workspace/governed-out/v150.2.0/linux-arm64'
  # shellcheck disable=SC2086
  docker run $common --network none --cap-drop ALL --security-opt no-new-privileges \
    -e GOVERNED_NETWORK_MODE=none \
    -e GITHUB_RUN_ID="${GITHUB_RUN_ID:-local-unassigned}" \
    "$image" sh scripts/governed/build_arm64_offline.sh
}

copy_out() {
  carrier_exists || { echo "missing builder carrier: $carrier" >&2; exit 1; }
  destination="$root/governed-out/v150.2.0"
  mkdir -p "$destination"
  if [ -e "$destination/linux-arm64" ]; then
    rm -rf "$destination/linux-arm64"
  fi
  docker cp "$carrier:/workspace/governed-out/v150.2.0/linux-arm64" "$destination/"
  echo "copied verified arm64 bundle from $volume"
}

case "$mode" in
  seed) seed ;;
  prefetch) prefetch ;;
  build) build ;;
  copy-out) copy_out ;;
  all)
    seed
    prefetch
    build
    copy_out
    ;;
  status)
    printf 'head=%s\nvolume=%s\ncarrier=%s\n' "$head" "$volume" "$carrier"
    docker volume inspect "$volume"
    ;;
  *)
    echo "usage: $0 {seed|prefetch|build|copy-out|all|status}" >&2
    exit 2
    ;;
esac
