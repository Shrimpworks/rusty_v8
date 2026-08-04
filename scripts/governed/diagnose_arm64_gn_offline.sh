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
cp "$fixture/probe.py" "$target/project/probe.py"

help_log="$out/gn-help-args.txt"
gen_log="$out/gn-gen.txt"

(cd "$target/project" && "$gn" help args) >"$help_log" 2>&1
(cd "$target/project" && "$gn" --script-executable=python3 gen out) >"$gen_log" 2>&1

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
probe without-script-executable "$gn" args "$absolute_out" --list
probe without-script-executable-option-first "$gn" args --list "$absolute_out"
probe with-script-executable "$gn" --script-executable=python3 args "$absolute_out" --list
probe with-script-executable-option-first "$gn" --script-executable=python3 args --list "$absolute_out"

without_script_status=$(cat "$out/without-script-executable.exit-status")
without_script_option_first_status=$(cat "$out/without-script-executable-option-first.exit-status")
with_script_status=$(cat "$out/with-script-executable.exit-status")
with_script_option_first_status=$(cat "$out/with-script-executable-option-first.exit-status")
set +e
grep -Fq '[str(gn), "--script-executable=python3", "args", str(GN_OUT), "--list"]' \
  "$root/scripts/governed/collect_arm64_evidence.py"
collector_command_status=$?
set -e
printf '%s\n' "$collector_command_status" > "$out/collector-command.exit-status"

cp "$cache/prefetch-evidence.json" "$out/prefetch-evidence.json"
route_sha=$(sha256sum /proc/net/route | awk '{print $1}')
export DIAGNOSTIC_ROUTE_SHA="$route_sha"
export WITHOUT_SCRIPT_STATUS="$without_script_status"
export WITHOUT_SCRIPT_OPTION_FIRST_STATUS="$without_script_option_first_status"
export WITH_SCRIPT_STATUS="$with_script_status"
export WITH_SCRIPT_OPTION_FIRST_STATUS="$with_script_option_first_status"
export COLLECTOR_COMMAND_STATUS="$collector_command_status"
python3 -c 'import json,os,pathlib; pathlib.Path("/workspace/governed-out/v150.2.0/linux-arm64-gn-diagnostic/result.json").write_text(json.dumps({"schemaVersion":1,"profile":"linux-arm64-release-simdutf-v1","purpose":"arm64-gn-script-executable-diagnostic","sourceCommit":os.environ.get("GITHUB_SHA","local-unassigned"),"runId":os.environ.get("GITHUB_RUN_ID","local-unassigned"),"networkMode":os.environ["GOVERNED_NETWORK_MODE"],"procNetRouteSha256":os.environ["DIAGNOSTIC_ROUTE_SHA"],"statuses":{"withoutScriptExecutable":int(os.environ["WITHOUT_SCRIPT_STATUS"]),"withoutScriptExecutableOptionFirst":int(os.environ["WITHOUT_SCRIPT_OPTION_FIRST_STATUS"]),"withScriptExecutable":int(os.environ["WITH_SCRIPT_STATUS"]),"withScriptExecutableOptionFirst":int(os.environ["WITH_SCRIPT_OPTION_FIRST_STATUS"]),"collectorCommand":int(os.environ["COLLECTOR_COMMAND_STATUS"])},"fullArm64BuildRan":False,"unsigned":True,"published":False,"admitted":False},indent=2,sort_keys=True)+"\n")'
(cd "$out" && sha256sum ./*.exit-status ./*.txt ./prefetch-evidence.json ./result.json > sha256sums.txt)
total=$(find "$out" -type f -exec wc -c {} \; | awk '{sum += $1} END {print sum + 0}')
test "$total" -le 1048576
printf 'arm64-gn-diagnostic without-script=%s without-script-option-first=%s with-script=%s with-script-option-first=%s collector-command=%s total-bytes=%s\n' \
  "$without_script_status" "$without_script_option_first_status" "$with_script_status" "$with_script_option_first_status" "$collector_command_status" "$total"

test "$without_script_status" -ne 0
test "$without_script_option_first_status" -ne 0
test "$with_script_status" -eq 0
test "$with_script_option_first_status" -eq 0
test "$collector_command_status" -eq 0
grep -q '^governed_arm64_gn_probe$' "$out/with-script-executable.txt"
grep -q 'Current value.*"expected"' "$out/with-script-executable.txt"
printf 'arm64-gn-script-executable-correction=proven\n'
