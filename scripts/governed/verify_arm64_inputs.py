#!/usr/bin/env python3
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message):
    print(f"governed arm64 input verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_digest(value, label):
    digest = value.removeprefix("sha256:")
    if not HEX64.fullmatch(digest):
        fail(f"{label} is not a SHA-256 digest")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-submodules", action="store_true")
    args = parser.parse_args()
    source = json.loads((GOV / "source.lock.json").read_text())
    builder = json.loads((GOV / "builder-linux-arm64.lock.json").read_text())
    expected = json.loads((GOV / "expected-outputs-linux-arm64.json").read_text())
    verification_blocker = json.loads(
        (GOV / "arm64-clean-build-blocker-verification.json").read_text()
    )
    linker_runtime_blocker = json.loads(
        (GOV / "arm64-clean-build-blocker-linker-runtime.json").read_text()
    )
    sysroot_link_blocker = json.loads(
        (GOV / "arm64-clean-build-blocker-sysroot-link.json").read_text()
    )
    evidence_collection_blocker = json.loads(
        (GOV / "arm64-clean-build-blocker-evidence-collection.json").read_text()
    )

    baseline = source["upstream"]
    if git("rev-parse", f'{baseline["commit"]}^{{tree}}') != baseline["tree"]:
        fail("upstream commit/tree mismatch")
    if git("merge-base", "HEAD", baseline["commit"]) != baseline["commit"]:
        fail("HEAD is not based on the governed upstream baseline")
    if git("rev-parse", "a31b8f39dc6933d5635367e8ccb67d70f2cc2385^{tree}") != git(
        "rev-parse", "a43ee7486c3e05bce5d6e5db586b3e2e688c33cf^{tree}"
    ):
        fail("merged governed baseline no longer matches the reviewed follow-up tree")
    if not git("merge-base", "--is-ancestor", "a31b8f39dc6933d5635367e8ccb67d70f2cc2385", "HEAD") == "":
        fail("HEAD does not descend from the exact merged governed baseline")
    if git("rev-parse", "eddede228a9214c4dfb6a85aeca22abc0679100d^{tree}") != git(
        "rev-parse", "c774d71b9b1d0021a5283b07d9185d6ec4d41b95^{tree}"
    ):
        fail("merged arm64 baseline no longer matches the reviewed PR #3 tree")
    if not git("merge-base", "--is-ancestor", "eddede228a9214c4dfb6a85aeca22abc0679100d", "HEAD") == "":
        fail("HEAD does not descend from the exact merged arm64 baseline")

    actual_links = {}
    for line in git("ls-files", "-s").splitlines():
        mode, oid, _stage, path = line.split(maxsplit=3)
        if mode == "160000":
            actual_links[path] = oid
    locked_links = {item["path"]: item["commit"] for item in source["gitlinks"]}
    if len(locked_links) != 20 or actual_links != locked_links:
        fail("the exact 20-gitlink source closure differs from source.lock.json")

    modules = git("config", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.url$")
    urls = {}
    for line in modules.splitlines():
        key, url = line.split(maxsplit=1)
        name = key[len("submodule.") : -len(".url")]
        path = git("config", "--file", ".gitmodules", "--get", f"submodule.{name}.path")
        urls[path] = url
    if urls != {item["path"]: item["url"] for item in source["gitlinks"]}:
        fail(".gitmodules URLs differ from source.lock.json")

    if args.require_submodules:
        for path, oid in locked_links.items():
            worktree = ROOT / path
            try:
                actual = git("rev-parse", "HEAD", cwd=worktree)
            except (subprocess.CalledProcessError, FileNotFoundError):
                fail(f"submodule is not an initialized checkout: {path}")
            if actual != oid:
                fail(f"submodule {path} is {actual}, expected {oid}")

    required = {
        "profile": "linux-arm64-release-simdutf-v1",
        "buildPlatform": "linux/amd64",
        "targetPlatform": "linux/arm64",
        "target": "aarch64-unknown-linux-gnu",
        "method": "cross",
    }
    for key, value in required.items():
        if builder.get(key) != value:
            fail(f"unexpected {key}: {builder.get(key)!r}")
    if builder["builderImage"]["linuxAmd64Digest"] != "sha256:307d198027388f780db83929487de35084a73ecbaa31319989438db38103439f":
        fail("unexpected builder image platform digest")
    if builder["cargo"]["toolchain"] != "1.91.0" or builder["cargo"]["target"] != required["target"]:
        fail("unexpected Rust toolchain or target")
    if builder["cargo"]["hostToolchainPath"] != "/usr/local/rustup/toolchains/1.91.0-x86_64-unknown-linux-gnu":
        fail("unexpected builder-image Rust toolchain path")
    cross_toolchain = builder["crossToolchain"]
    if cross_toolchain.get("linkerWrapper") != "scripts/governed/link_arm64.sh" or cross_toolchain.get(
        "linkerSysroot"
    ) != "/workspace/.governed-cache-arm64/cross":
        fail("unexpected ARM64 linker wrapper or extracted sysroot")
    for path_key, digest_key in (
        ("linkerWrapper", "linkerWrapperSha256"),
        ("linkProbeSource", "linkProbeSourceSha256"),
    ):
        path = ROOT / cross_toolchain[path_key]
        require_digest(cross_toolchain[digest_key], digest_key)
        if sha256(path) != cross_toolchain[digest_key]:
            fail(f"{path_key} differs from its governed digest")
    environment = builder["environment"]
    if "BINDGEN_EXTRA_CLANG_ARGS" in environment:
        fail("global bindgen arguments would leak into Chromium host tools")
    if environment["RUSTY_V8_GLIBC_SYSROOT"] != (
        "/workspace/.governed-cache-arm64/cross/usr/aarch64-linux-gnu"
    ):
        fail("unexpected arm64 bindgen target/header closure")
    if environment["RUSTY_V8_BINDGEN_RESOURCE_DIR"] != (
        "/workspace/.governed-cache-arm64/llvm19/usr/lib/llvm-19/lib/clang/19"
    ):
        fail("unexpected arm64 bindgen resource directory")
    if environment["CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER"] != (
        "/workspace/scripts/governed/link_arm64.sh"
    ):
        fail("Cargo must use the governed ARM64 sysroot linker wrapper")
    if environment["LD_LIBRARY_PATH"] != (
        "/workspace/.governed-cache-arm64/llvm19/usr/lib/x86_64-linux-gnu:"
        "/workspace/.governed-cache-arm64/cross/usr/lib/x86_64-linux-gnu"
    ):
        fail("unexpected host library path for bindgen and the pinned cross linker")
    for key in ("rustcCommit", "cargoCommit"):
        if not re.fullmatch(r"[0-9a-f]{40}", builder["cargo"][key]):
            fail(f"invalid {key}")
    if builder["claims"] != {"unsigned": True, "admitted": False, "published": False, "independentBuilder": False}:
        fail("arm64 claims must remain unsigned, unpublished, unadmitted, and non-independent")
    if verification_blocker.get("governedForkCommit") != "aa921fa48901bf28774d61248b0187c8b91c55a4":
        fail("post-build verification blocker is not bound to the exact failed head")
    execution = verification_blocker.get("execution", {})
    if execution.get("runId") != 30859318722 or execution.get("jobId") != 91837612159:
        fail("post-build verification blocker is not bound to the exact failed run/job")
    failure = verification_blocker.get("failure", {})
    if failure.get("phase") != "fixed-get-version-verification" or failure.get("diagnosticRetained") is not False:
        fail("post-build verification blocker does not retain the diagnostic gap")
    if linker_runtime_blocker.get("governedForkCommit") != "31e7bd74d7bdca699be175c7f598eeaa1383ff1e":
        fail("linker runtime blocker is not bound to the exact diagnostic head")
    linker_execution = linker_runtime_blocker.get("execution", {})
    if linker_execution.get("runId") != 30867826822 or linker_execution.get("jobId") != 91863398357:
        fail("linker runtime blocker is not bound to the exact failed run/job")
    linker_failure = linker_runtime_blocker.get("failure", {})
    if linker_failure.get("phase") != "fixed-test-compile" or "libbfd-2.40-arm64.so" not in linker_failure.get(
        "diagnostic", ""
    ):
        fail("linker runtime blocker does not retain the exact missing library diagnostic")
    if sysroot_link_blocker.get("governedForkCommit") != "9c9181dd09da445294462b43b69f0b37240f0e9b":
        fail("sysroot-link blocker is not bound to the exact corrected head")
    sysroot_execution = sysroot_link_blocker.get("execution", {})
    if sysroot_execution.get("runId") != 30873208247 or sysroot_execution.get("jobId") != 91879247103:
        fail("sysroot-link blocker is not bound to the exact failed run/job")
    sysroot_failure = sysroot_link_blocker.get("failure", {})
    if sysroot_failure.get("phase") != "fixed-test-compile" or sysroot_failure.get("missingAbsolutePaths") != [
        "/usr/aarch64-linux-gnu/lib/ld-linux-aarch64.so.1",
        "/usr/aarch64-linux-gnu/lib/libc.so.6",
        "/usr/aarch64-linux-gnu/lib/libc_nonshared.a",
    ]:
        fail("sysroot-link blocker does not retain the exact absolute-path diagnostic")
    if evidence_collection_blocker.get("governedForkCommit") != "343d1590df1615fb269036b23e3ca6f6aff81284":
        fail("evidence-collection blocker is not bound to the exact working ARM64 build head")
    evidence_execution = evidence_collection_blocker.get("execution", {})
    if evidence_execution.get("runId") != 30911205915 or evidence_execution.get("jobId") != 91998224324:
        fail("evidence-collection blocker is not bound to the exact failed run/job")
    evidence_stages = evidence_collection_blocker.get("observedStages", {})
    if not all(
        evidence_stages.get(key) == 0
        for key in (
            "arm64LinkProbeExitStatus",
            "arm64LinkProbeReadelfExitStatus",
            "arm64LinkProbeQemuExitStatus",
            "cargoBuildExitStatus",
            "fixedTestCompileExitStatus",
            "fixedTestReadelfExitStatus",
            "fixedTestQemuExitStatus",
        )
    ):
        fail("evidence-collection blocker does not retain all passing ARM64 build/test stages")
    if evidence_stages.get("fixedTestMachine") != "AArch64" or evidence_stages.get("fixedGetVersionPassed") is not True:
        fail("evidence-collection blocker does not retain the AArch64 get_version success")
    evidence_failure = evidence_collection_blocker.get("failure", {})
    expected_failed_command = [
        "/workspace/.governed-cache-arm64/gn/gn",
        "args",
        "/workspace/target/governed-v150.2.0-linux-arm64/aarch64-unknown-linux-gnu/release/gn_out",
        "--list",
    ]
    if evidence_failure.get("phase") != "evidence-collection" or evidence_failure.get("command") != expected_failed_command:
        fail("evidence-collection blocker does not retain the exact failed GN command")
    evidence_artifact = evidence_collection_blocker.get("boundedArtifact", {})
    if evidence_artifact.get("sha256") != "214632058b5c02d9c371cefc610fe58d73458221efc718d89096f7148c89b5a7" or evidence_artifact.get(
        "internalChecksumsVerified"
    ) is not True:
        fail("evidence-collection blocker artifact identity is not retained and verified")

    artifacts = [builder["clang"], builder["cargo"]["targetStandardLibrary"], builder["v8RustToolchain"]]
    artifacts.extend(builder["llvm19Bindgen"]["packages"])
    artifacts.extend(builder["sysroots"])
    for artifact in artifacts:
        require_digest(artifact["sha256"], artifact.get("name", artifact.get("role", artifact["url"])))
        if "size" in artifact and (not isinstance(artifact["size"], int) or artifact["size"] <= 0):
            fail(f"invalid artifact size for {artifact.get('url')}")
    require_digest(builder["cargo"]["targetStandardLibrary"]["channelManifestSha256"], "Rust channel manifest")
    require_digest(builder["gn"]["archiveSha256"], "GN archive")
    require_digest(builder["ninja"]["archiveSha256"], "Ninja archive")

    packages = builder["crossToolchain"]["packages"]
    names = [item["name"] for item in packages]
    if names != sorted(names) or len(names) != len(set(names)):
        fail("cross-toolchain package names must be sorted and unique")
    required_packages = {
        "binutils-aarch64-linux-gnu",
        "g++-12-aarch64-linux-gnu",
        "gcc-12-aarch64-linux-gnu",
        "libc6-dev-arm64-cross",
        "libstdc++-12-dev-arm64-cross",
        "linux-libc-dev-arm64-cross",
        "qemu-user-static",
    }
    if not required_packages.issubset(names):
        fail("cross compiler, linker, sysroot, C++, or emulator closure is incomplete")
    for package in packages:
        require_digest(package["sha256"], package["name"])
        if package["size"] <= 0 or not package["path"].startswith("pool/main/"):
            fail(f"invalid cross-toolchain package record: {package['name']}")

    files = expected["files"]
    output_names = [item["name"] for item in files]
    if output_names != sorted(output_names) or len(output_names) != len(set(output_names)):
        fail("arm64 expected outputs must be sorted and unique")
    if expected["profile"] != builder["profile"] or expected["maxTotalBytes"] <= 0:
        fail("arm64 output profile or total cap is invalid")
    if any(item["maxBytes"] <= 0 or item["maxBytes"] > expected["maxTotalBytes"] for item in files):
        fail("arm64 per-file output cap is invalid")

    for relative, expected_digest in builder["preservedLinuxAmd64Contract"].items():
        path = ROOT / relative
        if sha256(path) != expected_digest:
            fail(f"existing Linux/amd64 contract changed: {relative}")

    print(
        f"verified arm64 profile from baseline {baseline['commit']}, "
        f"{len(locked_links)} gitlinks, {len(packages)} cross packages, "
        f"and preserved Linux/amd64 contract"
    )


if __name__ == "__main__":
    main()
