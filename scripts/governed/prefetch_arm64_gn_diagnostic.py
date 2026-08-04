#!/usr/bin/env python3
import json
import pathlib
import shutil
import subprocess

import prefetch_arm64

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"
CACHE = ROOT / ".governed-cache-arm64-gn-diagnostic"
LOCK = json.loads((GOV / "builder-linux-arm64.lock.json").read_text())


def main():
    subprocess.run([str(ROOT / "scripts/governed/verify_arm64_inputs.py")], check=True)
    shutil.rmtree(CACHE, ignore_errors=True)
    CACHE.mkdir()
    prefetch_arm64.CACHE = CACHE
    prefetch_arm64.cipd(LOCK["gn"], CACHE / "gn")
    archive = CACHE / "downloads" / f"{LOCK['gn']['archiveSha256']}.zip"
    actual = prefetch_arm64.digest(archive)
    if actual != LOCK["gn"]["archiveSha256"]:
        raise SystemExit("diagnostic GN archive differs from the governed lock")
    evidence = {
        "schemaVersion": 1,
        "profile": LOCK["profile"],
        "purpose": "arm64-gn-evidence-command-diagnostic",
        "package": LOCK["gn"]["package"],
        "version": LOCK["gn"]["version"],
        "instanceId": LOCK["gn"]["instanceId"],
        "archiveSha256": actual,
    }
    (CACHE / "prefetch-evidence.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    )
    print(f"prefetched exact diagnostic GN archive sha256={actual}")


if __name__ == "__main__":
    main()
