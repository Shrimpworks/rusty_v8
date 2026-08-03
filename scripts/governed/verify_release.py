#!/usr/bin/env python3
import gzip
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fail(message):
    print(f"governed release verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main():
    if len(sys.argv) != 2:
        fail("usage: verify_release.py BUNDLE_DIRECTORY")
    bundle = pathlib.Path(sys.argv[1]).resolve()
    expected = set(json.loads((GOV / "expected-outputs.json").read_text())["files"])
    actual = {path.name for path in bundle.iterdir() if path.is_file()}
    if actual != expected:
        fail(f"bundle file set differs: expected={sorted(expected)} actual={sorted(actual)}")
    manifest = json.loads((bundle / "release-manifest.json").read_text())
    if manifest.get("admitted") is not False or manifest.get("unsigned") is not True:
        fail("bootstrap manifest must be unsigned and unadmitted")
    for name, record in manifest["files"].items():
        path = bundle / name
        if not path.is_file() or sha(path) != record["sha256"] or path.stat().st_size != record["size"]:
            fail(f"manifest mismatch for {name}")
    subjects = {item["name"]: item["digest"]["sha256"] for item in json.loads((bundle / "provenance.intoto.json").read_text())["subject"]}
    sums = {}
    for line in (bundle / "artifact-sha256sums.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    if subjects != sums:
        fail("provenance subjects differ from artifact checksum set")
    for name, digest in sums.items():
        if sha(bundle / name) != digest:
            fail(f"artifact digest mismatch for {name}")
    verification = (bundle / "fixed-verification.txt").read_text()
    if "test get_version ... ok" not in verification or "test result: ok" not in verification:
        fail("fixed get_version verification did not pass")
    with tempfile.TemporaryDirectory() as temp:
        archive = pathlib.Path(temp) / "librusty_v8.a"
        with gzip.open(bundle / "librusty_v8_simdutf_release_x86_64-unknown-linux-gnu.a.gz", "rb") as source:
            archive.write_bytes(source.read())
        members = subprocess.check_output(["ar", "t", archive], text=True).splitlines()
        if not members:
            fail("static archive has no members")
    print(f"verified governed bundle with {len(expected)} files and {len(members)} archive members")


if __name__ == "__main__":
    main()
