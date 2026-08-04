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
locked `libc6-dev-arm64-cross` archive with its declared SHA-256. Prefetch and
build now refuse a closure missing the relevant glibc headers.

The first header-path correction at
`c92651bf4986817d36039154724030e87c8a1d5b` was deliberately dispatched from
draft PR #4 and is retained as `arm64-clean-build-blocker-gn-bindgen.json`.
Prefetch passed, but the profile-wide `BINDGEN_EXTRA_CLANG_ARGS` also reached
Chromium's x64 host-tool bindgen action. That action retained its correct
`--target=x86_64-unknown-linux-gnu` and `-msse3` arguments, then the leaked final
arm64 target override made Clang reject the x64 flag at Ninja action 36 of 4,337.
The build stopped before any intermediate archive, fixed test, bundle, or
upload.

The next correction removes global bindgen state. The final rusty_v8 binding
builder alone reads the governed glibc sysroot and libclang resource-directory
variables; Chromium's generated host and target bindgen actions remain
unchanged. No package, digest, source gitlink, output cap, amd64 contract, or
network policy changes.

That correction was exercised at exact fork head
`aa921fa48901bf28774d61248b0187c8b91c55a4` in GitHub Actions run
`30859318722`, job `91837612159`, retained as
`arm64-clean-build-blocker-verification.json`. The empty-cache,
network-disabled Cargo release build completed in 94 minutes 37 seconds, which
also proves the final governed bindgen correction completed. The subsequent
fixed `get_version` Cargo command exited 101 before evidence collection. Its
output had been redirected to the ephemeral target directory, and shell
fail-fast handling stopped before printing or uploading it, so the exact
compile/link/QEMU subfailure is deliberately recorded as unavailable rather
than inferred. No verified bundle or artifact resulted.

The next attempt separates test compilation, pinned cross-`readelf` AArch64
identity, explicit pinned-QEMU execution, evidence collection, and bundle
verification into individually logged stages. Every stage prints its exit
status. A failure emits only a bounded diagnostic artifact; the complete
unsigned, unpublished, unadmitted candidate bundle remains success-only. No
LLVM, source, package, digest, object-cache, output-cap, or networking change is
made by this diagnostic correction. Full arm64 success remains unclaimed until
one new clean attempt completes every stage.

That diagnostic attempt ran at exact fork head
`31e7bd74d7bdca699be175c7f598eeaa1383ff1e` in GitHub Actions run
`30867826822`, job `91863398357`, and is retained as
`arm64-clean-build-blocker-linker-runtime.json`. Digest-pinned prefetch and the
empty-cache, network-disabled Cargo release build completed; the latter took 81
minutes 18 seconds and again completed V8 compilation and final rusty_v8
bindgen. The separated `cargo test --no-run` stage reached the final link, where
the pinned cross-linker's own loader exited 127 because its host-side
`libbfd-2.40-arm64.so` was absent. The stage returned Cargo status 101. No test
binary existed, so readelf, QEMU, evidence collection, bundle verification, and
the full-bundle upload correctly did not run. The sole bounded blocker artifact
verified internally and has GitHub SHA-256
`e08b662b1a5f582fb48ee2c04bb3821cc8830971b65c029532caadebd3a2008f`.

Independent inspection of the already declared
`binutils-aarch64-linux-gnu=2.40-2` archive at its locked SHA-256 confirms that
it already contains `usr/lib/x86_64-linux-gnu/libbfd-2.40-arm64.so`. No new
package is needed. Prefetch now refuses a closure without that exact library,
and the offline build exposes only the existing extracted cross-linker host
library directory in addition to the existing LLVM bindgen directory. This
correction does not change any input digest, LLVM, source, target sysroot,
networking, object-cache policy, or output cap. ARM64 success remains unclaimed
pending a new clean run.

That new run used exact fork head
`9c9181dd09da445294462b43b69f0b37240f0e9b` in GitHub Actions run
`30873208247`, job `91879247103`, and is retained as
`arm64-clean-build-blocker-sysroot-link.json`. Contract verification and
digest-pinned prefetch passed. The empty-cache, network-disabled Cargo release
build completed in 77 minutes 42 seconds, and the fixed-test compile reached
the final ARM64 link. This confirms the cross linker's host runtime-path fix.
The linker then exited 1 because the pinned glibc `libc.so` linker script names
`/usr/aarch64-linux-gnu/lib/libc.so.6`, `libc_nonshared.a`, and
`ld-linux-aarch64.so.1` as absolute paths, while the governed Debian closure is
extracted beneath `/workspace/.governed-cache-arm64/cross`. Cargo returned 101.
No test binary existed, so readelf, QEMU, evidence collection, bundle
verification, and full-bundle upload correctly did not run.

The sole bounded blocker artifact verified internally and has GitHub SHA-256
`fbc73421f1b3f4eb544124c4ffe02314e4bc8e58db7da702c23b78a2e9c82159`.
Independent inspection of the exact locked `libc6-arm64-cross` and
`libc6-dev-arm64-cross` bytes confirms both the absolute linker-script entries
and all three referenced files beneath the extracted closure. No package is
missing. The next exact boundary is to supply the already pinned GCC linker
with `--sysroot=/workspace/.governed-cache-arm64/cross`, retain explicit checks
for all three files, and rerun one clean network-disabled ARM64 build. This is
not an LLVM, V8, source, package, digest, networking, or object-cache change.

The correction routes Cargo's ARM64 link commands through a governed wrapper
that invokes the existing pinned `aarch64-linux-gnu-gcc-12` with
`--sysroot=/workspace/.governed-cache-arm64/cross`. Prefetch and the decisive
build both refuse a closure missing any of the three glibc linker-script
members. Before the long V8 compile, the network-disabled container compiles a
fixed benign C program, verifies its AArch64 ELF identity with the pinned
cross-`readelf`, and executes it with the pinned QEMU/sysroot pair. These early
stages retain bounded logs on failure and do not replace the final fixed
`get_version` test. No package, digest, LLVM, V8 source, Rust toolchain, target
sysroot contents, networking, cache, or output cap is changed. Full ARM64
success remains unclaimed until every final stage and bundle verification pass.

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
