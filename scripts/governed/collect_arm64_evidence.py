#!/usr/bin/env python3
import gzip
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"
CACHE = ROOT / ".governed-cache-arm64"
OUT = ROOT / "governed-out" / "v150.2.0" / "linux-arm64"
TARGET = ROOT / "target" / "governed-v150.2.0-linux-arm64"
GN_OUT = TARGET / "aarch64-unknown-linux-gnu" / "release" / "gn_out"
LOCK = json.loads((GOV / "builder-linux-arm64.lock.json").read_text())
EPOCH = 1784209467


def run(args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True)


def run_with_diagnostics(args, cwd=ROOT):
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        print(completed.stdout, end="", file=sys.stderr)
        completed.check_returncode()
    return completed.stdout


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_tar(source, destination):
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
                    relative = path.relative_to(source)
                    info = archive.gettarinfo(str(path), arcname=str(relative))
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = EPOCH
                    if path.is_file():
                        with path.open("rb") as handle:
                            archive.addfile(info, handle)
                    else:
                        archive.addfile(info)


def export_git_tree(repo, revision, destination):
    destination.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.tar"
    with temporary.open("wb") as output:
        subprocess.run(["git", "archive", revision], cwd=repo, check=True, stdout=output)
    with tarfile.open(temporary) as archive:
        archive.extractall(destination)
    temporary.unlink()


def export_sources(destination):
    export_git_tree(ROOT, "HEAD", destination / "rusty_v8")
    source_lock = json.loads((GOV / "source.lock.json").read_text())
    for item in source_lock["gitlinks"]:
        export_git_tree(ROOT / item["path"], item["commit"], destination / "rusty_v8" / item["path"])
    cargo_sources = CACHE / "cargo-home" / "registry" / "src"
    if not cargo_sources.is_dir():
        raise SystemExit("prefetched Cargo registry source closure is missing")
    shutil.copytree(cargo_sources, destination / "cargo-registry", symlinks=True)


def is_notice(path):
    upper = path.name.upper()
    return upper.startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS", "COPYRIGHT")) or path.name == "README.chromium"


def copy_notices(source, destination, prefix):
    if not source.exists():
        return
    for path in source.rglob("*"):
        if path.is_file() and is_notice(path):
            target = destination / prefix / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def artifact_materials():
    records = []

    def add(uri, digest):
        records.append({"uri": uri, "digest": {"sha256": digest.removeprefix("sha256:")}})

    add(LOCK["clang"]["url"], LOCK["clang"]["sha256"])
    target_std = LOCK["cargo"]["targetStandardLibrary"]
    add(target_std["channelManifestUrl"], target_std["channelManifestSha256"])
    add(target_std["url"], target_std["sha256"])
    add(LOCK["v8RustToolchain"]["url"], LOCK["v8RustToolchain"]["sha256"])
    for item in LOCK["llvm19Bindgen"]["packages"]:
        add(item["url"], item["sha256"])
    for item in LOCK["sysroots"]:
        add(item["url"], item["sha256"])
    for item in LOCK["crossToolchain"]["packages"]:
        add(f"{LOCK['crossToolchain']['snapshot']}/{item['path']}", item["sha256"])
    add(f"cipd://{LOCK['gn']['package']}@{LOCK['gn']['instanceId']}", LOCK["gn"]["archiveSha256"])
    add(f"cipd://{LOCK['ninja']['package']}@{LOCK['ninja']['instanceId']}", LOCK["ninja"]["archiveSha256"])
    return records


def sbom_components(cargo_lock, source_lock):
    components = []
    for package in cargo_lock["package"]:
        component = {
            "type": "library",
            "name": package["name"],
            "version": package["version"],
            "bom-ref": f"cargo:{package['name']}@{package['version']}",
        }
        if "checksum" in package:
            component["hashes"] = [{"alg": "SHA-256", "content": package["checksum"]}]
        if "source" in package:
            component["externalReferences"] = [{"type": "distribution", "url": package["source"]}]
        components.append(component)
    for item in source_lock["gitlinks"]:
        components.append(
            {
                "type": "library",
                "name": item["path"],
                "version": item["commit"],
                "bom-ref": f"git:{item['path']}@{item['commit']}",
                "externalReferences": [{"type": "vcs", "url": item["url"]}],
            }
        )
    for index, material in enumerate(artifact_materials()):
        components.append(
            {
                "type": "application",
                "name": material["uri"].rsplit("/", 1)[-1],
                "version": material["digest"]["sha256"][:16],
                "bom-ref": f"build-input:{index}:{material['digest']['sha256']}",
                "hashes": [{"alg": "SHA-256", "content": material["digest"]["sha256"]}],
                "externalReferences": [{"type": "distribution", "url": material["uri"]}],
            }
        )
    return sorted(components, key=lambda item: item["bom-ref"])


def spdx_id(value):
    return "SPDXRef-" + re.sub(r"[^A-Za-z0-9.-]", "-", value)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    raw_archive = GN_OUT / "obj" / "librusty_v8.a"
    binding = GN_OUT / "src_binding.rs"
    if not raw_archive.exists() or not binding.exists():
        raise SystemExit("governed arm64 build outputs are missing")
    binary = OUT / "librusty_v8_simdutf_release_aarch64-unknown-linux-gnu.a.gz"
    with raw_archive.open("rb") as source, binary.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0, compresslevel=9) as zipped:
            shutil.copyfileobj(source, zipped)
    shutil.copy2(binding, OUT / "src_binding_simdutf_release_aarch64-unknown-linux-gnu.rs")
    shutil.copy2(TARGET / "fixed-verification.txt", OUT / "fixed-verification.txt")

    with tempfile.TemporaryDirectory() as temporary:
        temporary = pathlib.Path(temporary)
        sources = temporary / "source"
        export_sources(sources)
        normalized_tar(sources, OUT / "corresponding-source.tar.gz")

        notices = temporary / "notices"
        copy_notices(sources, notices, pathlib.Path("corresponding-source"))
        copy_notices(CACHE / "clang", notices, pathlib.Path("build-inputs/clang"))
        copy_notices(CACHE / "llvm19", notices, pathlib.Path("build-inputs/llvm19"))
        copy_notices(CACHE / "rust-toolchain", notices, pathlib.Path("build-inputs/rust-toolchain"))
        copy_notices(CACHE / "cross" / "usr/share/doc", notices, pathlib.Path("build-inputs/cross-toolchain"))
        copy_notices(pathlib.Path("/usr/share/doc"), notices, pathlib.Path("builder-image/usr-share-doc"))
        normalized_tar(notices, OUT / "licenses-notices.tar.gz")

        metadata = temporary / "metadata"
        metadata.mkdir()
        for name in ["args.gn", "build.ninja", "project.json", ".ninja_log", ".ninja_deps"]:
            source = GN_OUT / name
            if source.exists():
                shutil.copy2(source, metadata / name)
        ninja = CACHE / "ninja" / "ninja"
        gn = CACHE / "gn" / "gn"
        (metadata / "ninja-graph.dot").write_text(run([str(ninja), "-C", str(GN_OUT), "-t", "graph", "rusty_v8"]))
        (metadata / "ninja-deps.txt").write_text(run([str(ninja), "-C", str(GN_OUT), "-t", "deps", "rusty_v8"]))
        (metadata / "ninja-commands.txt").write_text(run([str(ninja), "-C", str(GN_OUT), "-t", "commands", "rusty_v8"]))
        (metadata / "gn-args-list.txt").write_text(
            run_with_diagnostics(
                [str(gn), "--script-executable=python3", "args", str(GN_OUT), "--list"]
            )
        )
        project = json.loads((GN_OUT / "project.json").read_text())
        target_label = "//:rusty_v8"
        if target_label not in project["targets"]:
            raise SystemExit(f"missing governed GN target: {target_label}")
        (metadata / "gn-target.json").write_text(json.dumps({target_label: project["targets"][target_label]}, indent=2, sort_keys=True) + "\n")
        (metadata / "generated-build-settings.json").write_text(json.dumps(project["build_settings"], indent=2, sort_keys=True) + "\n")
        shutil.copy2(TARGET / "governed-build.log", metadata / "governed-build.log")
        shutil.copy2(CACHE / "prefetch-evidence.json", metadata / "prefetch-evidence.json")
        shutil.copy2(CACHE / "clean-cache-proof.json", metadata / "clean-cache-proof.json")
        shutil.copy2(CACHE / "host-environment.json", metadata / "host-environment.json")
        shutil.copy2(GOV / "builder-linux-arm64.lock.json", metadata / "builder-linux-arm64.lock.json")
        shutil.copy2(GOV / "source.lock.json", metadata / "source.lock.json")
        (metadata / "archive-members.txt").write_text(run(["ar", "t", str(raw_archive)]))
        (metadata / "submodules.txt").write_text(run(["git", "submodule", "status", "--recursive"]))
        (metadata / "builder-package-manifest.txt").write_text(run(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"]))
        baseline = json.loads((GOV / "source.lock.json").read_text())["upstream"]["commit"]
        (metadata / "governed.patch").write_text(run(["git", "diff", "--binary", f"{baseline}...HEAD"]))
        versions = {
            "rustc": run([str(CACHE / "rust-toolchain/bin/rustc"), "--version", "--verbose"]),
            "cargo": run([str(CACHE / "rust-toolchain/bin/cargo"), "--version", "--verbose"]),
            "clang": run([str(CACHE / "clang/bin/clang"), "--version"]),
            "crossGcc": run([str(CACHE / "cross/usr/bin/aarch64-linux-gnu-gcc-12"), "--version"]),
            "crossGxx": run([str(CACHE / "cross/usr/bin/aarch64-linux-gnu-g++-12"), "--version"]),
            "crossLd": run([str(CACHE / "cross/usr/bin/aarch64-linux-gnu-ld"), "--version"]),
            "qemu": run([str(CACHE / "cross/usr/bin/qemu-aarch64-static"), "--version"]),
            "gn": run([str(gn), "--version"]),
            "ninja": run([str(ninja), "--version"]),
            "python": run(["python3", "--version"]),
        }
        (metadata / "tool-versions.json").write_text(json.dumps(versions, indent=2, sort_keys=True) + "\n")
        members = run(["ar", "t", str(raw_archive)]).splitlines()
        if not members:
            raise SystemExit("arm64 static archive has no members")
        first_object = metadata / "first-archive-member.o"
        with first_object.open("wb") as output:
            subprocess.run(["ar", "p", str(raw_archive), members[0]], check=True, stdout=output)
        (metadata / "archive-architecture.txt").write_text(run([str(CACHE / "cross/usr/bin/aarch64-linux-gnu-readelf"), "-h", str(first_object)]))
        first_object.unlink()
        normalized_tar(metadata, OUT / "build-metadata.tar.gz")

    cargo_lock = tomllib.loads((ROOT / "Cargo.lock").read_text())
    source_lock = json.loads((GOV / "source.lock.json").read_text())
    governed_head = run(["git", "rev-parse", "HEAD"]).strip()
    components = sbom_components(cargo_lock, source_lock)
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000015021",
        "version": 1,
        "metadata": {"component": {"type": "library", "name": "rusty_v8-governed-linux-arm64", "version": "150.2.0-1", "bom-ref": "rusty_v8-governed-linux-arm64@150.2.0-1"}},
        "components": components,
        "compositions": [{"aggregate": "incomplete", "assemblies": ["rusty_v8-governed-linux-arm64@150.2.0-1"]}],
    }
    (OUT / "sbom.cdx.json").write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n")

    spdx_packages = []
    for component in components:
        checksums = [{"algorithm": "SHA256", "checksumValue": item["content"]} for item in component.get("hashes", [])]
        refs = component.get("externalReferences", [])
        spdx_packages.append(
            {
                "SPDXID": spdx_id(component["bom-ref"]),
                "name": component["name"],
                "versionInfo": component["version"],
                "downloadLocation": refs[0]["url"] if refs else "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                **({"checksums": checksums} if checksums else {}),
            }
        )
    root_spdx = "SPDXRef-rusty-v8-governed-linux-arm64"
    spdx_packages.append({"SPDXID": root_spdx, "name": "rusty_v8-governed-linux-arm64", "versionInfo": "150.2.0-1", "downloadLocation": "NOASSERTION", "filesAnalyzed": False, "licenseConcluded": "NOASSERTION", "licenseDeclared": "MIT", "copyrightText": "NOASSERTION"})
    spdx = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "rusty_v8-governed-linux-arm64-150.2.0",
        "documentNamespace": f"https://github.com/dills122/rusty_v8/governance/spdx/{governed_head}/linux-arm64",
        "creationInfo": {"created": "2026-07-16T13:44:27Z", "creators": ["Tool: rusty_v8-governed-builder/1"]},
        "packages": sorted(spdx_packages, key=lambda item: item["SPDXID"]),
        "relationships": [{"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": root_spdx}],
    }
    (OUT / "sbom.spdx.json").write_text(json.dumps(spdx, indent=2, sort_keys=True) + "\n")

    subjects = [path for path in sorted(OUT.iterdir()) if path.name not in {"artifact-sha256sums.txt", "provenance.intoto.json", "release-manifest.json"}]
    (OUT / "artifact-sha256sums.txt").write_text("".join(f"{sha(path)}  {path.name}\n" for path in subjects))
    materials = [
        {"uri": "https://github.com/dills122/rusty_v8.git", "digest": {"gitCommit": governed_head}},
        {"uri": source_lock["upstream"]["repository"], "digest": {"gitCommit": source_lock["upstream"]["commit"]}},
        {"uri": "file:Cargo.lock", "digest": {"sha256": sha(ROOT / "Cargo.lock")}},
    ]
    materials.extend({"uri": item["url"], "digest": {"gitCommit": item["commit"]}} for item in source_lock["gitlinks"])
    materials.extend(artifact_materials())
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": path.name, "digest": {"sha256": sha(path)}} for path in subjects],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://github.com/dills122/rusty_v8/governed-build/linux-arm64/v1",
                "externalParameters": LOCK,
                "resolvedDependencies": materials,
            },
            "runDetails": {
                "builder": {"id": f"docker://rust@{LOCK['builderImage']['linuxAmd64Digest']}"},
                "metadata": {"invocationId": os.environ.get("GITHUB_RUN_ID", "local-unassigned")},
            },
        },
    }
    (OUT / "provenance.intoto.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    manifest_files = {path.name: {"sha256": sha(path), "size": path.stat().st_size} for path in sorted(OUT.iterdir()) if path.name != "release-manifest.json"}
    manifest = {"schemaVersion": 1, "profile": LOCK["profile"], "sourceCommit": governed_head, "unsigned": True, "published": False, "admitted": False, "independentBuilder": False, "files": manifest_files}
    (OUT / "release-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
