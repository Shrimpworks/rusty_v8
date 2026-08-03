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
    if builder["claims"] != {"unsigned": True, "admitted": False, "published": False, "independentBuilder": False}:
        fail("arm64 claims must remain unsigned, unpublished, unadmitted, and non-independent")

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
