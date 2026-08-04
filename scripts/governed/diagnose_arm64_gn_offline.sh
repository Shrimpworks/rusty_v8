#!/bin/sh
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
cache="$root/.governed-cache-arm64-gn-diagnostic"
target="$root/target/governed-v150.2.0-linux-arm64-gn-diagnostic"
out="$root/governed-out/v150.2.0/linux-arm64-gn-diagnostic"
fixture="$root/scripts/governed/fixtures/gn-args-diagnostic"
gn="$cache/gn/gn"

test "$(pwd)" = /workspace
test "${GOVERNED_NETWORK_MODE:-}" = none
test ! -e "$target"
test ! -e "$out"
test -x "$gn"
test -f "$cache/prefetch-evidence.json"
if awk 'NR > 1 && $2 == "00000000" { found=1 } END { exit found ? 0 : 1 }' /proc/net/route; then
  echo "default network route exists in the network-disabled GN diagnostic" >&2
  exit 1
fi

mkdir -p "$target/project" "$out"
cp "$fixture/.gn" "$target/project/.gn"
cp "$fixture/BUILDCONFIG.gn" "$target/project/BUILDCONFIG.gn"
cp "$fixture/BUILD.gn" "$target/project/BUILD.gn"

help_log="$out/gn-help-args.txt"
gen_log="$out/gn-gen.txt"

(cd "$target/project" && "$gn" help args) >"$help_log" 2>&1
(cd "$target/project" && "$gn" gen out) >"$gen_log" 2>&1

probe() {
  name=$1
  shift
  set +e
  (cd "$target/project" && "$@") >"$out/$name.txt" 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" > "$out/$name.exit-status"
}

absolute_out="$target/project/out"
probe exact-legacy-absolute "$gn" args "$absolute_out" --list
probe option-first-absolute "$gn" args --list "$absolute_out"
probe legacy-relative "$gn" args out --list
probe option-first-relative "$gn" args --list out

exact_status=$(cat "$out/exact-legacy-absolute.exit-status")
corrected_absolute_status=$(cat "$out/option-first-absolute.exit-status")
legacy_relative_status=$(cat "$out/legacy-relative.exit-status")
corrected_relative_status=$(cat "$out/option-first-relative.exit-status")

cp "$cache/prefetch-evidence.json" "$out/prefetch-evidence.json"
route_sha=$(sha256sum /proc/net/route | awk '{print $1}')
export DIAGNOSTIC_ROUTE_SHA="$route_sha"
export EXACT_STATUS="$exact_status"
export CORRECTED_ABSOLUTE_STATUS="$corrected_absolute_status"
export LEGACY_RELATIVE_STATUS="$legacy_relative_status"
export CORRECTED_RELATIVE_STATUS="$corrected_relative_status"
python3 -c 'import json,os,pathlib; pathlib.Path("/workspace/governed-out/v150.2.0/linux-arm64-gn-diagnostic/result.json").write_text(json.dumps({"schemaVersion":1,"profile":"linux-arm64-release-simdutf-v1","purpose":"arm64-gn-evidence-command-diagnostic","sourceCommit":os.environ.get("GITHUB_SHA","local-unassigned"),"runId":os.environ.get("GITHUB_RUN_ID","local-unassigned"),"networkMode":os.environ["GOVERNED_NETWORK_MODE"],"procNetRouteSha256":os.environ["DIAGNOSTIC_ROUTE_SHA"],"statuses":{"exactLegacyAbsolute":int(os.environ["EXACT_STATUS"]),"optionFirstAbsolute":int(os.environ["CORRECTED_ABSOLUTE_STATUS"]),"legacyRelative":int(os.environ["LEGACY_RELATIVE_STATUS"]),"optionFirstRelative":int(os.environ["CORRECTED_RELATIVE_STATUS"])},"fullArm64BuildRan":False,"unsigned":True,"published":False,"admitted":False},indent=2,sort_keys=True)+"\n")'
(cd "$out" && sha256sum ./*.exit-status ./*.txt ./prefetch-evidence.json ./result.json > sha256sums.txt)
total=$(find "$out" -type f -exec wc -c {} \; | awk '{sum += $1} END {print sum + 0}')
test "$total" -le 1048576
printf 'arm64-gn-diagnostic exact-legacy-absolute=%s option-first-absolute=%s legacy-relative=%s option-first-relative=%s total-bytes=%s\n' \
  "$exact_status" "$corrected_absolute_status" "$legacy_relative_status" "$corrected_relative_status" "$total"

if [ "$exact_status" -eq 0 ]; then
  echo "minimal GN output did not reproduce the exact failed invocation" >&2
  exit 1
fi
test "$corrected_absolute_status" -eq 0
grep -q '^governed_arm64_gn_probe$' "$out/option-first-absolute.txt"
grep -q 'Current value.*"expected"' "$out/option-first-absolute.txt"
printf 'arm64-gn-ordering-correction=proven\n'
