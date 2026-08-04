#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
TARGET = ROOT / "target" / "governed-v150.2.0-linux-arm64"
CACHE = ROOT / ".governed-cache-arm64"
MAX_LOG_BYTES = 262_144
MAX_TOTAL_BYTES = 2_097_152


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_tail(source, destination):
    if not source.is_file():
        return
    size = source.stat().st_size
    with source.open("rb") as handle:
        if size > MAX_LOG_BYTES:
            handle.seek(-MAX_LOG_BYTES, os.SEEK_END)
        data = handle.read(MAX_LOG_BYTES)
    destination.write_bytes(data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
    parser.add_argument("--exit-status", required=True, type=int)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()

    output = args.output.resolve()
    expected = (ROOT / "governed-out/v150.2.0/linux-arm64-blocker").resolve()
    if output != expected:
        raise SystemExit("unexpected arm64 blocker output directory")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    logs = {
        "governed-build.tail.log": TARGET / "governed-build.log",
        "fixed-test-compile.tail.log": TARGET / "fixed-test-compile.log",
        "fixed-test-readelf.tail.log": TARGET / "fixed-test-readelf.log",
        "fixed-test-qemu.tail.log": TARGET / "fixed-verification.txt",
        "evidence-collection.tail.log": TARGET / "evidence-collection.log",
        "bundle-verification.tail.log": TARGET / "bundle-verification.log",
    }
    for name, source in logs.items():
        copy_tail(source, output / name)

    evidence = {
        "clean-cache-proof.json": CACHE / "clean-cache-proof.json",
        "host-environment.json": CACHE / "host-environment.json",
        "prefetch-evidence.json": CACHE / "prefetch-evidence.json",
        "fixed-test-binary.path": TARGET / "fixed-test-binary.path",
        "fixed-test-binary-candidates.txt": TARGET / "fixed-test-binary-candidates.txt",
    }
    for name, source in evidence.items():
        if source.is_file():
            shutil.copy2(source, output / name)

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    record = {
        "schemaVersion": 1,
        "status": "BLOCKED",
        "claim": "no-verified-arm64-bundle-no-publication-no-admission",
        "profile": "linux-arm64-release-simdutf-v1",
        "sourceCommit": head,
        "execution": {
            "provider": "GitHub Actions" if os.environ.get("GITHUB_RUN_ID") else "controlled-local",
            "runId": os.environ.get("GITHUB_RUN_ID", "local-unassigned"),
            "networkMode": os.environ.get("GOVERNED_NETWORK_MODE"),
        },
        "failure": {"phase": args.phase, "exitStatus": args.exit_status},
        "limits": {
            "perLogTailBytes": MAX_LOG_BYTES,
            "maxTotalBytes": MAX_TOTAL_BYTES,
        },
        "claims": {
            "unsigned": True,
            "published": False,
            "admitted": False,
            "independentBuilder": False,
        },
    }
    (output / "blocker.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )

    files = sorted(path for path in output.iterdir() if path.is_file())
    total = sum(path.stat().st_size for path in files)
    if total > MAX_TOTAL_BYTES:
        raise SystemExit(f"arm64 blocker evidence exceeds {MAX_TOTAL_BYTES} bytes")
    (output / "blocker-sha256sums.txt").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in files)
    )
    final_total = sum(path.stat().st_size for path in output.iterdir())
    if final_total > MAX_TOTAL_BYTES:
        raise SystemExit(f"arm64 blocker evidence exceeds {MAX_TOTAL_BYTES} bytes")
    print(
        f"retained bounded arm64 blocker phase={args.phase} "
        f"exit-status={args.exit_status} files={len(list(output.iterdir()))} "
        f"bytes={final_total}"
    )


if __name__ == "__main__":
    main()
