#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"
CACHE = ROOT / ".governed-cache"
LOCK = json.loads((GOV / "builder.lock.json").read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url, expected, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and digest(destination) == expected:
        return
    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.unlink(missing_ok=True)
    with urllib.request.urlopen(url) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    actual = digest(temporary)
    if actual != expected:
        temporary.unlink(missing_ok=True)
        raise SystemExit(f"digest mismatch for {url}: {actual} != {expected}")
    temporary.replace(destination)


def safe_extract_tar(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:xz") as handle:
        root = destination.resolve()
        for member in handle.getmembers():
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise SystemExit(f"unsafe tar member: {member.name}")
        handle.extractall(destination)


def cipd(item, destination):
    query = urllib.parse.urlencode({"package_name": item["package"], "version": item["version"]})
    resolve = f"https://chrome-infra-packages.appspot.com/_ah/api/repo/v1/instance/resolve?{query}"
    with urllib.request.urlopen(resolve) as response:
        resolved = json.load(response)
    if resolved.get("instance_id") != item["instanceId"]:
        raise SystemExit(f"CIPD resolution changed for {item['package']}")
    query = urllib.parse.urlencode({"package_name": item["package"], "instance_id": item["instanceId"]})
    endpoint = f"https://chrome-infra-packages.appspot.com/_ah/api/repo/v1/instance?{query}"
    with urllib.request.urlopen(endpoint) as response:
        instance = json.load(response)
    archive = CACHE / "downloads" / f"{item['archiveSha256']}.zip"
    download(instance["fetch_url"], item["archiveSha256"], archive)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(archive) as package:
        package.extractall(destination)
    for path in destination.rglob("*"):
        if path.is_file() and path.name in {"gn", "ninja"}:
            path.chmod(path.stat().st_mode | 0o111)


def main():
    subprocess.run([str(ROOT / "scripts/governed/verify_inputs.py"), "--require-submodules"], check=True)
    CACHE.mkdir(exist_ok=True)

    clang_archive = CACHE / "downloads" / "clang.tar.xz"
    download(LOCK["clang"]["url"], LOCK["clang"]["sha256"], clang_archive)
    clang_dir = CACHE / "clang"
    if not (clang_dir / "bin" / "clang").exists():
        shutil.rmtree(clang_dir, ignore_errors=True)
        safe_extract_tar(clang_archive, clang_dir)

    rust_archive = CACHE / "downloads" / "v8-rust-toolchain.tar.xz"
    toolchain = LOCK["v8RustToolchain"]
    download(toolchain["url"], toolchain["sha256"], rust_archive)
    rust_dir = ROOT / "third_party" / "rust-toolchain"
    sentinel = rust_dir / ".rusty_v8_version"
    if not sentinel.exists() or sentinel.read_text() != toolchain["url"]:
        shutil.rmtree(rust_dir, ignore_errors=True)
        safe_extract_tar(rust_archive, rust_dir)
        sentinel.write_text(toolchain["url"])

    cipd(LOCK["gn"], CACHE / "gn")
    cipd(LOCK["ninja"], CACHE / "ninja")

    subprocess.run(["python3", "build/linux/sysroot_scripts/install-sysroot.py", "--arch=amd64"], cwd=ROOT, check=True)
    cargo_home = CACHE / "cargo-home"
    cargo_home.mkdir(exist_ok=True)
    env = os.environ | {
        "CARGO_HOME": str(cargo_home),
        "RUSTUP_TOOLCHAIN": "1.91.0-x86_64-unknown-linux-gnu",
    }
    # Fetch the complete lock, not only the selected target. Cargo metadata and
    # test target resolution can require locked, target-conditional packages
    # before compilation even when the final build has one target.
    subprocess.run(["cargo", "fetch", "--locked"], cwd=ROOT, env=env, check=True)

    evidence = {
        "schemaVersion": 1,
        "downloads": {
            "clang": digest(clang_archive),
            "v8RustToolchain": digest(rust_archive),
            "gn": digest(CACHE / "downloads" / f"{LOCK['gn']['archiveSha256']}.zip"),
            "ninja": digest(CACHE / "downloads" / f"{LOCK['ninja']['archiveSha256']}.zip"),
        },
    }
    (CACHE / "prefetch-evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print("prefetched and verified governed build inputs")


if __name__ == "__main__":
    main()
