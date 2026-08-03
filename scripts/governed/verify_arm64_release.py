#!/usr/bin/env python3
import gzip
import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"
CACHE = ROOT / ".governed-cache-arm64"


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message):
    print(f"governed arm64 release verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main():
    if len(sys.argv) != 2:
        fail("usage: verify_arm64_release.py BUNDLE_DIRECTORY")
    bundle = pathlib.Path(sys.argv[1]).resolve()
    expected_lock = json.loads((GOV / "expected-outputs-linux-arm64.json").read_text())
    builder_lock = json.loads((GOV / "builder-linux-arm64.lock.json").read_text())
    caps = {item["name"]: item["maxBytes"] for item in expected_lock["files"]}
    expected = set(caps)
    actual = {path.name for path in bundle.iterdir() if path.is_file()}
    if actual != expected:
        fail(f"bundle file set differs: expected={sorted(expected)} actual={sorted(actual)}")
    total_size = sum((bundle / name).stat().st_size for name in expected)
    if total_size > expected_lock["maxTotalBytes"]:
        fail(f"bundle exceeds total cap: {total_size} > {expected_lock['maxTotalBytes']}")
    for name, limit in caps.items():
        if (bundle / name).stat().st_size > limit:
            fail(f"{name} exceeds immutable cap {limit}")

    manifest = json.loads((bundle / "release-manifest.json").read_text())
    required_claims = {"unsigned": True, "published": False, "admitted": False, "independentBuilder": False}
    if any(manifest.get(key) != value for key, value in required_claims.items()):
        fail("manifest claims must remain unsigned, unpublished, unadmitted, and non-independent")
    if manifest.get("profile") != builder_lock["profile"]:
        fail("manifest profile differs from the arm64 builder lock")
    governed_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if manifest.get("sourceCommit") != governed_head:
        fail("manifest source commit differs from the governed checkout")
    if set(manifest.get("files", {})) != expected - {"release-manifest.json"}:
        fail("release manifest file inventory is incomplete or has extras")
    for name, record in manifest["files"].items():
        path = bundle / name
        if sha(path) != record["sha256"] or path.stat().st_size != record["size"]:
            fail(f"manifest mismatch for {name}")

    provenance = json.loads((bundle / "provenance.intoto.json").read_text())
    definition = provenance.get("predicate", {}).get("buildDefinition", {})
    if definition.get("externalParameters") != builder_lock:
        fail("provenance external parameters differ from the exact arm64 lock")
    if provenance.get("predicate", {}).get("runDetails", {}).get("builder", {}).get("id") != f"docker://rust@{builder_lock['builderImage']['linuxAmd64Digest']}":
        fail("provenance builder identity differs from the pinned platform image")
    materials = definition.get("resolvedDependencies", [])
    if not any(item.get("uri") == "https://github.com/dills122/rusty_v8.git" and item.get("digest", {}).get("gitCommit") == governed_head for item in materials):
        fail("provenance omits the exact governed fork source commit")
    if not any(item.get("uri") == builder_lock["cargo"]["targetStandardLibrary"]["url"] and item.get("digest", {}).get("sha256") == builder_lock["cargo"]["targetStandardLibrary"]["sha256"] for item in materials):
        fail("provenance omits the arm64 Rust standard-library input")

    subjects = {item["name"]: item["digest"]["sha256"] for item in provenance["subject"]}
    sums = {}
    for line in (bundle / "artifact-sha256sums.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    if subjects != sums:
        fail("provenance subjects differ from the artifact checksum set")
    for name, digest in sums.items():
        if sha(bundle / name) != digest:
            fail(f"artifact digest mismatch for {name}")

    verification = (bundle / "fixed-verification.txt").read_text()
    if "test get_version ... ok" not in verification or "test result: ok" not in verification:
        fail("fixed arm64 get_version verification did not pass")

    cdx = json.loads((bundle / "sbom.cdx.json").read_text())
    spdx = json.loads((bundle / "sbom.spdx.json").read_text())
    if cdx.get("bomFormat") != "CycloneDX" or cdx.get("specVersion") != "1.6" or not cdx.get("components"):
        fail("CycloneDX 1.6 SBOM is missing or empty")
    if spdx.get("spdxVersion") != "SPDX-2.3" or not spdx.get("packages"):
        fail("SPDX 2.3 SBOM is missing or empty")

    required_metadata = {
        "args.gn",
        "archive-architecture.txt",
        "archive-members.txt",
        "build.ninja",
        "builder-linux-arm64.lock.json",
        "clean-cache-proof.json",
        "generated-build-settings.json",
        "gn-args-list.txt",
        "gn-target.json",
        "governed-build.log",
        "governed.patch",
        "host-environment.json",
        "ninja-commands.txt",
        "ninja-deps.txt",
        "ninja-graph.dot",
        "prefetch-evidence.json",
        "project.json",
        "source.lock.json",
        "submodules.txt",
        "tool-versions.json",
    }
    with tempfile.TemporaryDirectory() as temporary:
        temporary = pathlib.Path(temporary)
        archive = temporary / "librusty_v8.a"
        with gzip.open(bundle / "librusty_v8_simdutf_release_aarch64-unknown-linux-gnu.a.gz", "rb") as source:
            archive.write_bytes(source.read())
        members = subprocess.check_output(["ar", "t", archive], text=True).splitlines()
        if not members:
            fail("arm64 static archive has no members")
        first_object = temporary / "first.o"
        with first_object.open("wb") as output:
            subprocess.run(["ar", "p", str(archive), members[0]], check=True, stdout=output)
        readelf = CACHE / "cross/usr/bin/aarch64-linux-gnu-readelf"
        header = subprocess.check_output([str(readelf), "-h", str(first_object)], text=True)
        if "Machine:" not in header or "AArch64" not in header:
            fail("static archive first object is not AArch64")

        with tarfile.open(bundle / "build-metadata.tar.gz", "r:gz") as metadata:
            names = {pathlib.PurePosixPath(item.name).name for item in metadata.getmembers() if item.isfile()}
            if not required_metadata.issubset(names):
                fail(f"build metadata is missing {sorted(required_metadata - names)}")
            metadata.extractall(temporary / "metadata")
        clean = json.loads((temporary / "metadata/clean-cache-proof.json").read_text())
        if clean != {
            "ccachePresent": False,
            "networkMode": "none",
            "outputDirectoryExisted": False,
            "procNetRouteSha256": clean.get("procNetRouteSha256"),
            "profile": builder_lock["profile"],
            "sccachePresent": False,
            "schemaVersion": 1,
            "targetDirectoryExisted": False,
        } or len(clean.get("procNetRouteSha256", "")) != 64:
            fail("clean-cache/network-none proof is invalid")
        host = json.loads((temporary / "metadata/host-environment.json").read_text())
        if host.get("targetPlatform") != "linux/arm64" or host.get("independentBuilder") is not False:
            fail("host evidence mislabels the target or independent-builder claim")
        architecture = (temporary / "metadata/archive-architecture.txt").read_text()
        if "Machine:" not in architecture or "AArch64" not in architecture:
            fail("retained archive architecture evidence is not AArch64")

        with tarfile.open(bundle / "corresponding-source.tar.gz", "r:gz") as source_archive:
            source_names = set(source_archive.getnames())
        if "rusty_v8/Cargo.toml" not in source_names or not any(name.startswith("rusty_v8/v8/") for name in source_names) or not any(name.startswith("cargo-registry/") for name in source_names):
            fail("corresponding source omits the superproject, V8 gitlink, or Cargo registry closure")
        with tarfile.open(bundle / "licenses-notices.tar.gz", "r:gz") as notices:
            notice_names = set(notices.getnames())
        if not any(name.startswith("corresponding-source/") for name in notice_names) or not any(name.startswith("build-inputs/cross-toolchain/") for name in notice_names):
            fail("license/notice bundle omits source or cross-toolchain notices")

    print(f"verified governed arm64 bundle with {len(expected)} files, {len(members)} archive members, and {total_size} capped bytes")


if __name__ == "__main__":
    main()
