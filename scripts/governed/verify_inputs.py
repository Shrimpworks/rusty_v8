#!/usr/bin/env python3
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOV = ROOT / "governance" / "v150.2.0"


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def fail(message):
    print(f"governed input verification failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-submodules", action="store_true")
    args = parser.parse_args()
    source = json.loads((GOV / "source.lock.json").read_text())
    builder = json.loads((GOV / "builder.lock.json").read_text())
    expected = json.loads((GOV / "expected-outputs.json").read_text())

    baseline = source["upstream"]
    if git("rev-parse", f'{baseline["commit"]}^{{tree}}') != baseline["tree"]:
        fail("upstream commit/tree mismatch")
    if git("merge-base", "HEAD", baseline["commit"]) != baseline["commit"]:
        fail("HEAD is not based directly on the governed upstream baseline")
    if git("show", f'{baseline["commit"]}:Cargo.lock'):
        pass

    actual_links = {}
    for line in git("ls-files", "-s").splitlines():
        mode, oid, _stage, path = line.split(maxsplit=3)
        if mode == "160000":
            actual_links[path] = oid
    locked_links = {item["path"]: item["commit"] for item in source["gitlinks"]}
    if actual_links != locked_links:
        fail(f"gitlink set differs from source.lock.json: {actual_links}")

    modules = git("config", "--file", ".gitmodules", "--get-regexp", r"^submodule\..*\.url$")
    urls = {}
    for line in modules.splitlines():
        key, url = line.split(maxsplit=1)
        name = key[len("submodule.") : -len(".url")]
        path = git("config", "--file", ".gitmodules", "--get", f"submodule.{name}.path")
        urls[path] = url
    locked_urls = {item["path"]: item["url"] for item in source["gitlinks"]}
    if urls != locked_urls:
        fail(".gitmodules URLs differ from source.lock.json")

    if args.require_submodules:
        for path, oid in locked_links.items():
            worktree = ROOT / path
            if not (worktree / ".git").exists() and not worktree.exists():
                fail(f"submodule is not initialized: {path}")
            try:
                actual = git("rev-parse", "HEAD", cwd=worktree)
            except (subprocess.CalledProcessError, FileNotFoundError):
                fail(f"submodule is not a checkout: {path}")
            if actual != oid:
                fail(f"submodule {path} is {actual}, expected {oid}")

    if builder["builderImage"]["linuxAmd64Digest"] != "sha256:307d198027388f780db83929487de35084a73ecbaa31319989438db38103439f":
        fail("unexpected builder image digest")
    names = expected["files"]
    if names != sorted(names) or len(names) != len(set(names)):
        fail("expected outputs must be sorted and unique")
    print(f"verified baseline {baseline['commit']} and {len(locked_links)} exact gitlinks")


if __name__ == "__main__":
    main()
