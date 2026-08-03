#!/usr/bin/env python3
import gzip
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"
OUT = ROOT / "governed-out" / "v150.2.0"
TARGET = ROOT / "target" / "governed-v150.2.0"
GN_OUT = TARGET / "x86_64-unknown-linux-gnu" / "release" / "gn_out"
EPOCH = 1784209467


def run(args, cwd=ROOT):
    return subprocess.check_output(args, cwd=cwd, text=True)


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalized_tar(source, destination):
    with destination.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as archive:
                for path in sorted(source.rglob("*"), key=lambda p: p.as_posix()):
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


def export_sources(destination):
    destination.mkdir(parents=True)
    subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, check=True, stdout=(destination / "root.tar").open("wb"))
    with tarfile.open(destination / "root.tar") as archive:
        archive.extractall(destination)
    (destination / "root.tar").unlink()
    lock = json.loads((GOV / "source.lock.json").read_text())
    for item in lock["gitlinks"]:
        subdir = destination / item["path"]
        subdir.mkdir(parents=True, exist_ok=True)
        temporary = destination / ".submodule.tar"
        subprocess.run(["git", "archive", item["commit"]], cwd=ROOT / item["path"], check=True, stdout=temporary.open("wb"))
        with tarfile.open(temporary) as archive:
            archive.extractall(subdir)
        temporary.unlink()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for path in OUT.iterdir():
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)

    raw_archive = GN_OUT / "obj" / "librusty_v8.a"
    binding = GN_OUT / "src_binding.rs"
    if not raw_archive.exists() or not binding.exists():
        raise SystemExit("governed build outputs are missing")
    binary = OUT / "librusty_v8_simdutf_release_x86_64-unknown-linux-gnu.a.gz"
    with raw_archive.open("rb") as source, binary.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0, compresslevel=9) as zipped:
            shutil.copyfileobj(source, zipped)
    shutil.copy2(binding, OUT / "src_binding_simdutf_release_x86_64-unknown-linux-gnu.rs")
    shutil.copy2(TARGET / "fixed-verification.txt", OUT / "fixed-verification.txt")

    with tempfile.TemporaryDirectory() as temp:
        temp = pathlib.Path(temp)
        sources = temp / "source"
        export_sources(sources)
        normalized_tar(sources, OUT / "corresponding-source.tar.gz")

        notices = temp / "notices"
        for path in sources.rglob("*"):
            upper = path.name.upper()
            if path.is_file() and (upper.startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS")) or path.name == "README.chromium"):
                target = notices / path.relative_to(sources)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        normalized_tar(notices, OUT / "licenses-notices.tar.gz")

        metadata = temp / "metadata"
        metadata.mkdir()
        for name in ["args.gn", "build.ninja", "project.json", ".ninja_log", ".ninja_deps"]:
            source = GN_OUT / name
            if source.exists():
                shutil.copy2(source, metadata / name)
        ninja = ROOT / ".governed-cache/ninja/ninja"
        gn = ROOT / ".governed-cache/gn/gn"
        (metadata / "ninja-graph.dot").write_text(run([str(ninja), "-C", str(GN_OUT), "-t", "graph", "rusty_v8"]))
        (metadata / "ninja-deps.txt").write_text(run([str(ninja), "-C", str(GN_OUT), "-t", "deps", "rusty_v8"]))
        project = json.loads((GN_OUT / "project.json").read_text())
        target_label = "//:rusty_v8"
        if target_label not in project["targets"]:
            raise SystemExit(f"missing governed GN target: {target_label}")
        (metadata / "gn-target.json").write_text(
            json.dumps({target_label: project["targets"][target_label]}, indent=2, sort_keys=True) + "\n"
        )
        (metadata / "generated-build-settings.json").write_text(
            json.dumps(project["build_settings"], indent=2, sort_keys=True) + "\n"
        )
        shutil.copy2(TARGET / "governed-build.log", metadata / "governed-build.log")
        (metadata / "archive-members.txt").write_text(run(["ar", "t", str(raw_archive)]))
        (metadata / "submodules.txt").write_text(run(["git", "submodule", "status", "--recursive"]))
        versions = {
            "rustc": run(["rustc", "--version", "--verbose"]),
            "cargo": run(["cargo", "--version", "--verbose"]),
            "clang": run([str(ROOT / ".governed-cache/clang/bin/clang"), "--version"]),
            "gn": run([str(gn), "--version"]),
            "ninja": run([str(ninja), "--version"]),
            "python": run(["python3", "--version"]),
        }
        (metadata / "tool-versions.json").write_text(json.dumps(versions, indent=2, sort_keys=True) + "\n")
        shutil.copy2(ROOT / ".governed-cache/prefetch-evidence.json", metadata / "prefetch-evidence.json")
        normalized_tar(metadata, OUT / "build-metadata.tar.gz")

    cargo_lock = tomllib.loads((ROOT / "Cargo.lock").read_text())
    source_lock = json.loads((GOV / "source.lock.json").read_text())
    governed_head = run(["git", "rev-parse", "HEAD"]).strip()
    components = []
    for package in cargo_lock["package"]:
        component = {"type": "library", "name": package["name"], "version": package["version"]}
        if "checksum" in package:
            component["hashes"] = [{"alg": "SHA-256", "content": package["checksum"]}]
        if "source" in package:
            component["externalReferences"] = [{"type": "distribution", "url": package["source"]}]
        components.append(component)
    for item in source_lock["gitlinks"]:
        components.append({
            "type": "library",
            "name": item["path"],
            "version": item["commit"],
            "externalReferences": [{"type": "vcs", "url": item["url"]}],
        })
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:00000000-0000-4000-8000-000000015020",
        "version": 1,
        "metadata": {"component": {"type": "library", "name": "rusty_v8-governed", "version": "150.2.0-1"}},
        "components": sorted(components, key=lambda c: (c["name"], c["version"])),
        "compositions": [{"aggregate": "incomplete", "assemblies": ["rusty_v8-governed@150.2.0-1"]}],
    }
    (OUT / "sbom.cdx.json").write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n")

    subjects = [path for path in sorted(OUT.iterdir()) if path.name not in {"artifact-sha256sums.txt", "provenance.intoto.json", "release-manifest.json"}]
    sums = "".join(f"{sha(path)}  {path.name}\n" for path in subjects)
    (OUT / "artifact-sha256sums.txt").write_text(sums)
    materials = [
        {
            "uri": "https://github.com/dills122/rusty_v8.git",
            "digest": {"gitCommit": governed_head},
        },
        {"uri": source_lock["upstream"]["repository"], "digest": {"gitCommit": source_lock["upstream"]["commit"]}},
    ]
    materials.extend({"uri": item["url"], "digest": {"gitCommit": item["commit"]}} for item in source_lock["gitlinks"])
    provenance = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{"name": path.name, "digest": {"sha256": sha(path)}} for path in subjects],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://github.com/dills122/rusty_v8/governed-build/v1",
                "externalParameters": json.loads((GOV / "builder.lock.json").read_text()),
                "resolvedDependencies": materials,
            },
            "runDetails": {"builder": {"id": "docker://rust@sha256:307d198027388f780db83929487de35084a73ecbaa31319989438db38103439f"}, "metadata": {"invocationId": os.environ.get("GITHUB_RUN_ID", "local-unassigned")}},
        },
    }
    (OUT / "provenance.intoto.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    manifest_files = {path.name: {"sha256": sha(path), "size": path.stat().st_size} for path in sorted(OUT.iterdir()) if path.name != "release-manifest.json"}
    manifest = {
        "schemaVersion": 1,
        "profile": "linux-amd64-release-simdutf-v1",
        "sourceCommit": governed_head,
        "unsigned": True,
        "admitted": False,
        "files": manifest_files,
    }
    (OUT / "release-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
