# Governed v150.2.0 build and publication contract

Status: bootstrap only. This contract does not admit a Capsule runtime, publish a
release, or claim equality with the historical upstream archive.

## Boundary

This line is based on official `denoland/rusty_v8` tag `v150.2.0`, commit
`d305e6afa7736f6e298c30ae6646f7709ee9382b`. The baseline branch is
`capsule/upstream-v150.2.0-d305e6a`; governed changes are reviewed against that
branch. Fork `main` is not moved or rewritten.

The first build profile is deliberately narrow:

- host and target: `linux/amd64` / `x86_64-unknown-linux-gnu`;
- release mode, `simdutf` enabled, pointer compression disabled;
- fixed workspace path `/workspace` and `SOURCE_DATE_EPOCH=1784209467`;
- exact official Rust 1.91.0 Bookworm builder image by platform digest;
- upstream-compatible LLVM 19.1.7 libclang, libLLVM, and builtin headers from
  apt.llvm.org, each pinned by version, URL, size, SHA-256, and source commit;
- networked input acquisition followed by a Docker `--network none` build;
- Cargo `--frozen`, offline mode, a fixed eight-job build, UTC and `C.UTF-8`.

Linux/arm64 is not silently substituted by this profile. It remains required
before Capsule can replace the retained Linux/arm64 archive evidence.

## Source and patch identity

`source.lock.json` is the normative gitlink closure. It keeps the exact
`denoland/v8` commit `ac1e23989121713ca642f6650b34deff7b686896`, whose
Chromium V8 base is `0da5ef4358784bb0af0ff5d5d7c49cdad8931d1e`
(V8 15.0.245.2), plus the exact ordered four-commit Deno patch chain. This
bootstrap does not modify V8 and therefore does not create or require a V8 fork.

`retained-pr56-evidence.json` records the historical official archive and
publisher identities established by Capsule PR #56. They are retained evidence,
not inputs or expected outputs of this builder.

## Build phases

Run from a checkout with all exact submodules initialized:

```sh
scripts/governed/run-builder.sh verify
scripts/governed/run-builder.sh prefetch
scripts/governed/run-builder.sh build
```

`prefetch` is the only phase with container network access. It verifies and
extracts digest-pinned Clang, LLVM 19 bindgen runtime, sysroot, V8 Rust
toolchain, GN and Ninja objects, then asks Cargo to fetch the complete
`Cargo.lock` closure. `build` uses the same pinned builder and verified
prefetched inputs with `--network none`.

## Required publication set

A build is publication-eligible only as one indivisible unsigned bundle:

- normalized `librusty_v8_simdutf_release_x86_64-unknown-linux-gnu.a.gz`;
- generated `src_binding_simdutf_release_x86_64-unknown-linux-gnu.rs`;
- `corresponding-source.tar.gz`, assembled from the exact superproject and all
  exact gitlinks;
- `licenses-notices.tar.gz`, containing every retained license, copying,
  notice, authors, and `README.chromium` file from that source set;
- `build-metadata.tar.gz`, including `args.gn`, `build.ninja`, the governed GN
  target from `project.json`, Ninja graph/dependencies, archive members, exact
  submodules, and tool versions;
- CycloneDX 1.6 `sbom.cdx.json`;
- unsigned in-toto `provenance.intoto.json` with exact materials and subjects;
- `artifact-sha256sums.txt`, `release-manifest.json`, and fixed verification
  output.

The workflow uploads this set only as a CI artifact. It has no release trigger,
release permission, signing step, Capsule integration, or admission authority.

## Verification and claims

`scripts/governed/verify_release.py` recomputes every enumerated digest, checks
the provenance subjects, refuses missing or extra bundle files, checks archive
membership, and requires the fixed upstream `get_version` test result.

One build proves only that the declared profile completed. Equality from two
directories on one host is same-host evidence. Independent-builder equality may
be claimed only after matching bundles are observed on separately controlled
hosts and the differing provenance materials are retained.

## Ownership and update policy

- Owner: `dills122/rusty_v8` maintainers; Capsule runtime/supply-chain reviewers
  approve governed changes and publication manifests.
- Advisories: monitor RustSec, GitHub advisories for this fork and
  `denoland/rusty_v8`, Chromium/V8 security releases, and material third-party
  component advisories. Affected unpublished candidates are discarded; affected
  published candidates remain unadmitted until rebuilt and reviewed.
- Updates: create a new immutable upstream baseline branch, regenerate every
  lock and evidence file, review the upstream/V8 patch delta, rebuild, and rerun
  verification. Never rebase or force-update a reviewed baseline or published
  tag.
- Patch removal: remove a Deno V8 patch only when the selected upstream V8 base
  contains an equivalent change, record the upstream commit, and rerun the full
  build/publication corpus. Do not silently reorder or squash the chain.
- V8 source changes: stop. Creating or governing a `denoland/v8` fork requires a
  separate owner decision and is outside this bootstrap authority.

## Remaining release blockers

- execute and retain one complete build of this bootstrap profile;
- add a fully pinned Linux/arm64 builder/profile and compare its governed output
  to the retained product candidate as applicable;
- reproduce on a separately controlled host before any independent-builder
  claim;
- review generated third-party notices and SBOM completeness;
- define immutable release storage, signing/custody, advisory response SLAs, and
  tag protection;
- assemble and verify the later governed Deno/runtime-root bundle;
- keep `RUNTIME-001` unsupported until a separate admission decision.
