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

Linux/arm64 is not silently substituted by this profile. The sibling profile
below adds the target without replacing, weakening, or relabeling Linux/amd64.

### Linux/arm64 sibling profile

`builder-linux-arm64.lock.json` defines
`linux-arm64-release-simdutf-v1` for target
`aarch64-unknown-linux-gnu`. The build platform is pinned Linux/amd64 and the
method is an x64-host to arm64-target cross build. This follows upstream's
supported CI shape. Upstream's V8 Arm64 Linux guidance explicitly calls native
Arm64 Linux unsupported, and this revision publishes its Chromium Clang and V8
Rust host tools only for Linux/x64. The owned Apple Silicon Docker environment
may execute the pinned x64 builder through Docker's platform support, but that
is same-host cross-build evidence and is never independent-builder evidence.

The sibling locks all additions needed beyond the unchanged amd64 contract:

- the existing official Rust 1.91.0 Bookworm Linux/amd64 builder by platform
  digest and exact internal rustc/Cargo paths and commit identities, plus the
  versioned Rust arm64 standard-library archive and the exact channel manifest
  that binds it; prefetch invokes the sealed toolchain binaries directly and
  never lets a rustup proxy expand the upstream multi-target toolchain file;
- the unchanged Chromium Clang, LLVM 19 bindgen runtime, V8 Rust host toolchain,
  GN, Ninja, and amd64 host sysroot;
- the Chromium arm64 target sysroot by URL, size, and SHA-256;
- a timestamped Debian Bookworm GCC 12/binutils/libc/libstdc++ cross-linker
  closure and static QEMU user-mode runner, with every package pinned by version,
  snapshot path, size, and SHA-256;
- the exact `Cargo.lock` closure, offline Cargo build, fixed eight-job build,
  UTC, `C.UTF-8`, and no compiler object cache.

The arm64 lock also records SHA-256 identities for the complete existing
Linux/amd64 lock and script set. Contract verification refuses any arm64 change
that alters those amd64 files.

## Source and patch identity

`source.lock.json` is the normative gitlink closure. It keeps the exact
`denoland/v8` commit `ac1e23989121713ca642f6650b34deff7b686896`, whose
Chromium V8 base is `0da5ef4358784bb0af0ff5d5d7c49cdad8931d1e`
(V8 15.0.245.2), plus the exact ordered four-commit Deno patch chain. This
bootstrap does not modify V8 and therefore does not create or require a V8 fork.

`retained-pr56-evidence.json` records the historical official archive and
publisher identities established by Capsule PR #56. They are retained evidence,
not inputs or expected outputs of this builder.

Capsule PR #62 is the canonical retained arm64 blocker record: reviewed head
`e85fb20495a601dfd1f49b4a7b764229b3c16056`, merged to Capsule `main` as
`4f1edd789ce91f720e98e743fb21dbe59493d26a`. That record grants no build
publication, signing, runtime admission, deployment, or product-wiring authority.

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

The sibling arm64 phases are separate and never read the amd64 target or object
cache:

```sh
scripts/governed/run-arm64-builder.sh verify
scripts/governed/run-arm64-builder.sh prefetch
scripts/governed/run-arm64-builder.sh build
```

Its connected phase downloads only the URLs or CIPD instances declared by the
arm64 lock and verifies every digest before extraction. Immediately before the
decisive phase, the runner removes only
`target/governed-v150.2.0-linux-arm64` and
`governed-out/v150.2.0/linux-arm64`. The network-disabled container refuses a
default route, `sccache`, `ccache`, any pre-existing target directory, or any
pre-existing arm64 output directory. Build, bindgen, the fixed `get_version`
test through the pinned QEMU runner, evidence collection, and bundle verification
all execute in that network-disabled phase.

On an owned Docker Desktop host that cannot bind-mount a macOS protected
checkout, `run-arm64-builder-volume.sh` is the equivalent isolated transport.
It refuses a dirty integration checkout, creates a new named volume scoped to
the exact fork head, copies that real checkout and its git metadata into the
volume, verifies the copied head/tree/submodules with networking disabled, and
then runs the same prefetch and decisive scripts. It refuses pre-existing volume
state during seeding and retains the volume identity in the handoff. The fork
checkout remains the only integration destination; the volume is build state,
not another branch or source of truth.

## Linux/amd64 required publication set

A build is publication-eligible only as one indivisible unsigned bundle:

- normalized `librusty_v8_simdutf_release_x86_64-unknown-linux-gnu.a.gz`;
- generated `src_binding_simdutf_release_x86_64-unknown-linux-gnu.rs`;
- `corresponding-source.tar.gz`, assembled from the exact superproject and all
  exact gitlinks;
- `licenses-notices.tar.gz`, containing every retained license, copying,
  notice, authors, and `README.chromium` file from that source set;
- `build-metadata.tar.gz`, including `args.gn`, the captured build log with
  `PRINT_GN_ARGS=1`, `build.ninja`, generated build settings and governed target
  from `project.json`, Ninja graph/dependencies, archive members, exact
  submodules, and tool versions;
- CycloneDX 1.6 `sbom.cdx.json`;
- unsigned in-toto `provenance.intoto.json` with the exact governed fork head,
  upstream/gitlink materials, and artifact subjects;
- `artifact-sha256sums.txt`, `release-manifest.json`, and fixed verification
  output.

The workflow uploads this set only as a CI artifact. It has no release trigger,
release permission, signing step, Capsule integration, or admission authority.

## Linux/arm64 required evidence set

The arm64 candidate is likewise one indivisible unsigned, unpublished, and
unadmitted bundle under `governed-out/v150.2.0/linux-arm64/`:

- normalized `librusty_v8_simdutf_release_aarch64-unknown-linux-gnu.a.gz` and
  generated `src_binding_simdutf_release_aarch64-unknown-linux-gnu.rs`;
- corresponding source for the exact superproject, 20 gitlinks, and fetched
  Cargo registry sources;
- complete available source, Cargo, cross-toolchain, LLVM/Clang, Rust-toolchain,
  and builder-image license/copyright/notice files;
- effective `args.gn`, `build.ninja`, `project.json` settings/target metadata,
  Ninja graph/deps/commands, build log, archive inventory and AArch64 ELF header,
  exact patch, submodules, tools, builder packages, prefetched-input digests,
  physical/Docker host record, and clean-cache/network-none proof;
- CycloneDX 1.6 and SPDX 2.3 SBOMs, unsigned in-toto provenance bound to the
  exact fork head/profile/inputs/outputs, checksums, fixed verification, and the
  release manifest.

`expected-outputs-linux-arm64.json` fixes the exact file set, per-file maximums,
and a 2 GiB total cap. Exceeding a cap is a verification failure; caps are not
raised during a build to make an output pass.

The GitHub arm64 job exposes connected prefetch and decisive network-disabled
build as separate workflow steps. Cargo/V8 output is streamed while also being
retained byte-for-byte as the governed build log; this changes observability,
not the empty-cache or network boundary.

## Verification and claims

`scripts/governed/verify_release.py` recomputes every enumerated digest, checks
the provenance subjects, refuses missing or extra bundle files, checks archive
membership, and requires the fixed upstream `get_version` test result.

`scripts/governed/verify_arm64_release.py` additionally requires the exact arm64
profile and builder inputs, validates both SBOM formats, verifies the clean-cache
and network-none records, requires the corresponding-source/license closures,
and uses the pinned cross `readelf` to reject an archive whose first object is
not AArch64.

One build proves only that the declared profile completed. Equality from two
directories on one host is same-host evidence. Independent-builder equality may
be claimed only after matching bundles are observed on separately controlled
hosts and the differing provenance materials are retained.

The governed workflow runs both source/lock contracts on every pull request to
the immutable baseline branch. The expensive arm64 job is deliberately gated:
it is skipped while a pull request is draft, starts when the pull request is
made ready for review, and can also be invoked explicitly with workflow-dispatch
mode `full-arm64`. A skipped draft job is not build success. The workflow has
read-only repository permission, a digest-pinned upload action, and no release,
signing, or admission step.

## Observed Linux/arm64 result

The exact clean attempt at governed fork commit
`e84e27bee18b39194225ab5c0e19551983fc1659` is retained as
`arm64-clean-build-blocker.json`. Digest-only prefetch completed with 263 Cargo
archives. The decisive container began with empty arm64 target/output state, no
compiler object cache, and networking disabled. It then stopped before GN
generation because `build.rs` checked a legacy `debian_sid_arm64-sysroot` path;
the upstream installer did not find its URL `.stamp` in the already-extracted
locked Bullseye arm64 sysroot and attempted the same locked URL. Network-none
enforcement refused that request. No archive, binding, fixed test, evidence
bundle, publication, signing, or admission resulted.

Prefetch now writes the installer-compatible exact URL stamp after verifying
and extracting each locked sysroot. This deterministic handoff correction does
not add an input or enable build networking.

The next exact clean attempt ran on GitHub Actions from reviewed fork head
`c774d71b9b1d0021a5283b07d9185d6ec4d41b95`, merged to the governed baseline
as `eddede228a9214c4dfb6a85aeca22abc0679100d`. It is retained separately as
`arm64-clean-build-blocker-bindgen.json`. Digest-pinned prefetch again completed
with 263 Cargo archives. The network-disabled cold V8 build then completed all
4,337 Ninja actions and created an intermediate `librusty_v8.a`, but bindgen
selected `/usr/include/features-time64.h` from the host header set and could not
resolve target header `bits/wordsize.h`. Cargo therefore failed closed before
the fixed test, evidence bundle, upload, publication, signing, or admission.

The required target header was independently confirmed inside the already
locked `libc6-dev-arm64-cross` archive with its declared SHA-256. The follow-up
bindgen correction explicitly selects `aarch64-linux-gnu` and that pinned target
include directory, and prefetch/build now refuse a closure missing the relevant
glibc headers. No package, digest, source gitlink, output cap, amd64 contract, or
network policy changes. Full arm64 success remains unclaimed until the gated job
completes from a new clean state.

## Ownership and update policy

- Owner: `dills122/rusty_v8` maintainers; Capsule runtime/supply-chain reviewers
  approve governed changes and publication manifests.
- Review routing: `.github/CODEOWNERS` requests `@dills122` review for the
  governed locks, scripts, workflow, and CODEOWNERS itself. Required-review and
  branch-protection enforcement remains a repository setting and is not claimed
  solely from this file.
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
- execute and retain one complete clean Linux/arm64 build, fixed test, and bundle
  verification before comparing it to the retained product candidate;
- reproduce on a separately controlled host before any independent-builder
  claim;
- review generated third-party notices and SBOM completeness;
- define immutable release storage, signing/custody, advisory response SLAs, and
  tag protection;
- assemble and verify the later governed Deno/runtime-root bundle;
- keep `RUNTIME-001` unsupported until a separate admission decision.
