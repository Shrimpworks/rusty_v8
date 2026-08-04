#!/usr/bin/env python3
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.parse
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"
CACHE = ROOT / ".governed-cache-arm64"
LOCK = json.loads((GOV / "builder-linux-arm64.lock.json").read_text())


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def download(url, expected, destination, expected_size=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and digest(destination) == expected:
        if expected_size is None or destination.stat().st_size == expected_size:
            return
    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "rusty-v8-governed-prefetch/1"})
    with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    actual = digest(temporary)
    if actual != expected:
        temporary.unlink(missing_ok=True)
        raise SystemExit(f"digest mismatch for {url}: {actual} != {expected}")
    if expected_size is not None and temporary.stat().st_size != expected_size:
        actual_size = temporary.stat().st_size
        temporary.unlink(missing_ok=True)
        raise SystemExit(f"size mismatch for {url}: {actual_size} != {expected_size}")
    temporary.replace(destination)


def safe_extract_tar(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:*") as handle:
        root = destination.resolve()
        members = handle.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise SystemExit(f"unsafe tar member: {member.name}")
        handle.extractall(destination, members=members)


def safe_extract_zip(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise SystemExit(f"unsafe zip member: {member.filename}")
        package.extractall(destination)


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
    shutil.rmtree(destination, ignore_errors=True)
    safe_extract_zip(archive, destination)
    for path in destination.rglob("*"):
        if path.is_file() and path.name in {"gn", "ninja"}:
            path.chmod(path.stat().st_mode | 0o111)


def install_sysroots(downloads):
    for item in LOCK["sysroots"]:
        archive = CACHE / "downloads" / f"sysroot-{item['arch']}.tar.xz"
        download(item["url"], item["sha256"], archive, item["size"])
        destination = ROOT / item["directory"]
        shutil.rmtree(destination, ignore_errors=True)
        safe_extract_tar(archive, destination)
        # build.rs checks a legacy debian_sid_* path and may call the upstream
        # installer even though the lock's bullseye directory is present. The
        # installer itself uses this exact URL stamp to prove the declared
        # sysroot is already installed and return without network access.
        (destination / ".stamp").write_text(item["url"])
        downloads[f"sysroot-{item['arch']}"] = digest(archive)


def install_rust_target(downloads):
    target = LOCK["cargo"]["targetStandardLibrary"]
    manifest = CACHE / "downloads" / "channel-rust-1.91.0.toml"
    download(target["channelManifestUrl"], target["channelManifestSha256"], manifest)
    manifest_data = tomllib.loads(manifest.read_text())
    manifest_target = manifest_data["pkg"]["rust-std"]["target"][LOCK["target"]]
    if manifest_target["xz_url"] != target["url"] or manifest_target["xz_hash"] != target["sha256"]:
        raise SystemExit("Rust channel manifest does not bind the locked arm64 standard library")

    archive = CACHE / "downloads" / "rust-std-aarch64-unknown-linux-gnu.tar.xz"
    download(target["url"], target["sha256"], archive, target["size"])
    toolchain = CACHE / "rust-toolchain"
    source_toolchain = pathlib.Path(LOCK["cargo"]["hostToolchainPath"])
    rustc_version = subprocess.check_output(
        [str(source_toolchain / "bin/rustc"), "--version", "--verbose"], text=True
    )
    cargo_version = subprocess.check_output(
        [str(source_toolchain / "bin/cargo"), "--version", "--verbose"], text=True
    )
    if LOCK["cargo"]["rustcCommit"] not in rustc_version or LOCK["cargo"]["rustcLlvmVersion"] not in rustc_version:
        raise SystemExit("builder image Rust compiler differs from the arm64 lock")
    if LOCK["cargo"]["cargoCommit"] not in cargo_version:
        raise SystemExit("builder image Cargo differs from the arm64 lock")
    shutil.rmtree(toolchain, ignore_errors=True)
    shutil.copytree(source_toolchain, toolchain, symlinks=True)
    with tempfile.TemporaryDirectory() as temporary:
        temporary = pathlib.Path(temporary)
        safe_extract_tar(archive, temporary)
        installer = temporary / "rust-std-1.91.0-aarch64-unknown-linux-gnu" / "install.sh"
        subprocess.run(
            ["sh", str(installer), f"--prefix={toolchain}", "--disable-ldconfig"],
            check=True,
        )
    rustlib = toolchain / "lib" / "rustlib" / LOCK["target"] / "lib"
    if not rustlib.is_dir() or not any(rustlib.glob("libstd-*.rlib")):
        raise SystemExit("locked arm64 Rust standard library was not installed")
    downloads["rust-channel-manifest"] = digest(manifest)
    downloads["rust-std-aarch64"] = digest(archive)


def install_cross_toolchain(downloads):
    cross = CACHE / "cross"
    shutil.rmtree(cross, ignore_errors=True)
    cross.mkdir(parents=True)
    base = LOCK["crossToolchain"]["snapshot"].rstrip("/")
    for package in LOCK["crossToolchain"]["packages"]:
        archive = CACHE / "downloads" / f"{package['sha256']}.deb"
        download(f"{base}/{package['path']}", package["sha256"], archive, package["size"])
        subprocess.run(["dpkg-deb", "--extract", str(archive), str(cross)], check=True)
        downloads[f"debian:{package['name']}={package['version']}"] = digest(archive)
    required = [
        cross / "usr/bin/aarch64-linux-gnu-gcc-12",
        cross / "usr/bin/aarch64-linux-gnu-g++-12",
        cross / "usr/bin/aarch64-linux-gnu-readelf",
        cross / "usr/bin/qemu-aarch64-static",
        cross / "usr/lib/x86_64-linux-gnu/libbfd-2.40-arm64.so",
        cross / "usr/aarch64-linux-gnu/lib/ld-linux-aarch64.so.1",
        cross / "usr/aarch64-linux-gnu/include/features.h",
        cross / "usr/aarch64-linux-gnu/include/features-time64.h",
        cross / "usr/aarch64-linux-gnu/include/bits/wordsize.h",
    ]
    for path in required:
        if not path.exists():
            raise SystemExit(f"cross-toolchain closure is missing {path.relative_to(cross)}")


def main():
    subprocess.run([str(ROOT / "scripts/governed/verify_arm64_inputs.py"), "--require-submodules"], check=True)
    CACHE.mkdir(exist_ok=True)
    downloads = {}

    clang = LOCK["clang"]
    clang_archive = CACHE / "downloads" / "clang.tar.xz"
    download(clang["url"], clang["sha256"], clang_archive, clang["size"])
    clang_dir = CACHE / "clang"
    shutil.rmtree(clang_dir, ignore_errors=True)
    safe_extract_tar(clang_archive, clang_dir)
    downloads["clang"] = digest(clang_archive)

    llvm19_root = CACHE / "llvm19"
    shutil.rmtree(llvm19_root, ignore_errors=True)
    llvm19_root.mkdir(parents=True)
    for package in LOCK["llvm19Bindgen"]["packages"]:
        archive = CACHE / "downloads" / f"{package['sha256']}.deb"
        download(package["url"], package["sha256"], archive, package["size"])
        subprocess.run(["dpkg-deb", "--extract", str(archive), str(llvm19_root)], check=True)
        downloads[f"llvm19:{package['name']}"] = digest(archive)

    toolchain = LOCK["v8RustToolchain"]
    rust_archive = CACHE / "downloads" / "v8-rust-toolchain.tar.xz"
    download(toolchain["url"], toolchain["sha256"], rust_archive, toolchain["size"])
    rust_dir = ROOT / "third_party" / "rust-toolchain"
    shutil.rmtree(rust_dir, ignore_errors=True)
    safe_extract_tar(rust_archive, rust_dir)
    (rust_dir / ".rusty_v8_version").write_text(toolchain["url"])
    downloads["v8-rust-toolchain"] = digest(rust_archive)

    cipd(LOCK["gn"], CACHE / "gn")
    cipd(LOCK["ninja"], CACHE / "ninja")
    downloads["gn"] = digest(CACHE / "downloads" / f"{LOCK['gn']['archiveSha256']}.zip")
    downloads["ninja"] = digest(CACHE / "downloads" / f"{LOCK['ninja']['archiveSha256']}.zip")

    install_sysroots(downloads)
    install_rust_target(downloads)
    install_cross_toolchain(downloads)

    cargo_home = CACHE / "cargo-home"
    cargo_home.mkdir(exist_ok=True)
    host_toolchain = pathlib.Path(LOCK["cargo"]["hostToolchainPath"])
    env = os.environ | {
        "CARGO_HOME": str(cargo_home),
        "RUSTC": str(host_toolchain / "bin/rustc"),
    }
    subprocess.run([str(host_toolchain / "bin/cargo"), "fetch", "--locked"], cwd=ROOT, env=env, check=True)
    cargo_archives = {
        str(path.relative_to(cargo_home)): digest(path)
        for path in sorted(cargo_home.rglob("*.crate"))
    }
    if not cargo_archives:
        raise SystemExit("Cargo prefetch did not retain any crate archives")

    evidence = {
        "schemaVersion": 1,
        "profile": LOCK["profile"],
        "downloads": dict(sorted(downloads.items())),
        "cargoLockSha256": digest(ROOT / "Cargo.lock"),
        "cargoArchives": cargo_archives,
    }
    (CACHE / "prefetch-evidence.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(f"prefetched and verified arm64 inputs and {len(cargo_archives)} Cargo archives")


if __name__ == "__main__":
    main()
