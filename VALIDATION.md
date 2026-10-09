# Validation record — 2026-10-09

This record distinguishes compilation, Linux-host ABI simulation, and real
OpenHarmony execution. **No OpenHarmony SDK-linked binary or actual device has
been executed for this change.** The port remains experimental and the core PR is a draft. This repository
contains build automation only; historical core results below do not establish
validation for a different source revision. Exact GitHub SDK results are
recorded below.

## Go 1.27.2 update: verification in progress

The new default core is
[`b637b8617624655906b737977f50de5280bf7f65`](https://github.com/ZxillyFork/go-hmos/commit/b637b8617624655906b737977f50de5280bf7f65),
a non-rewriting merge of upstream Go 1.27.2
[`022c8636110ebac86a9b88724cda168ed713c21f`](https://github.com/golang/go/commit/022c8636110ebac86a9b88724cda168ed713c21f)
into the previously reviewed port. The version is `go1.27.2-hmos-devel`.
The previous core and the upstream release are both ancestors of the new pin;
all prior port changes are retained. No build automation or installer was
added to the core repository.

Relative to upstream base `68fa7699a27d745f90bf8630202e1a415d1b0769`, this
imports ten security-fix commits plus the release-version commit:
CVE-2026-56857, CVE-2026-56866, CVE-2026-78659, CVE-2026-78663,
CVE-2026-78667, CVE-2026-78669, CVE-2026-94439, CVE-2026-94440,
CVE-2026-97031, and CVE-2026-97032. The other Go 1.27.2 changes were already
present in that previous upstream base.

The bootstrap is updated to official Go 1.27.2. The Linux/amd64 archive was
verified against the official SHA-256
`ecbadb99091a3f46e31f5f934b068b1864eafa7995211b39eaddf76996045fe5`.
This revision adds full host-package tests for `crypto/tls`, `net/textproto`,
`mime/multipart`, `net/http`, `net/http/httputil`, and `net/http/internal/http2`,
selected `os.Root` regressions, and a race-enabled
`TestServer_HeaderTableSizeDuringWrite`. Standard-library behavioral tests use
`src/go.mod` in module mode: GOPATH mode incorrectly selects Go 1.20 GODEBUG
compatibility defaults. An offline command-environment regression checks this.
The separate installer executes the
installed fork's selected `os.Root` regressions on Linux, macOS, and Windows;
Windows must report explicit passes for dangling-junction mkdir cases.
Linux and cross-compilation cannot establish Windows junction behavior.
These checks do not claim a complexity benchmark for HTTP/2 SETTINGS handling.

Current validation is pending. Do not attribute the successful historical
runs below to this revision. Exact-source host, SDK, installer-matrix results,
and remaining limitations will be recorded here when established.

## Historical Go 1.27.1 results

The sections below preserve the earlier evidence and its exact source hashes.

## Passed locally

- Complete three-stage `src/make.bash` bootstrap on Linux/amd64, using official
  Go 1.27.1 as `GOROOT_BOOTSTRAP` (GOMAXPROCS=4).
  Official bootstrap archive SHA-256:
  `63d339f0da5ab53635a56f2490a7984dfe12dfcff22ad749f63edaf590168445`.
- Focused tests: `internal/platform`, `internal/buildcfg`, `go/build`,
  `cmd/go/internal/imports`, `cmd/go/internal/modindex`, `cmd/internal/obj`,
  `cmd/internal/objabi`, `cmd/go/internal/cfg`, `cmd/go/internal/envcmd`,
  `cmd/go/internal/work`, and `cmd/go/internal/toolchain`.
- Independent review ran the API compatibility check with the new downstream
  API baseline, ARM64/AMD64 code-generation tests, and the
  `TestScript/build_openharmony` command-driver test. The script verifies both
  missing-cgo rejection and fail-closed toolchain auto-switching.
- Linux runtime signal/GODEBUG, runtime/cgo and CPU-profile regression tests;
  Windows/amd64 runtime test cross-compilation; Linux/arm64 and Darwin/arm64
  and amd64 runtime cross-compilation.
- `GOOS=openharmony` runtime **Go/assembly** compilation for ARM64 and AMD64.
  This does not compile/link against the OHOS SDK C library.
- Shell syntax checks for SDK download/build helpers. Missing required SDK
  inputs fail rather than falling back to a host compiler.

## Linux-host ABI simulations (not OHOS validation)

Compiled `GOOS=openharmony GOARCH=amd64 CGO_ENABLED=1` with **host GCC/glibc**,
using `-ldflags=-extldflags=-fuse-ld=bfd` where needed. These are deliberately
not described as SDK builds:

- c-shared output contains real `R_X86_64_TLSDESC` and no initial-exec TLS flag.
- `dlopen` fixture: pre-load environment/GODEBUG, 100 callbacks from four
  foreign pthreads, goroutines, GC, timers, recovered nil faults, and existing
  reserved-signal handler preservation passed.
- Network checks were explicitly omitted with `--no-network`: this execution
  environment rejects netlink. An **unmodified official Go** `net.Interfaces`
  probe also returns `operation not permitted`. The first full loader run
  failed on that check; it was not reclassified as a network pass.
- The inherited 39-bit ARM64 heap ceiling was removed after review found no
  platform-wide ABI guarantee. Upstream 48-bit handling and a regression
  assertion are retained; both target runtime packages were recompiled.
- Target runtime-policy/synchronous-fault tests and the explicit CPU-profile
  rejection test passed under the host loader.
- Target PIE hello executable ran; a target-built native `cmd/go` ran and
  reported `GOOS=openharmony`, `GOHOSTOS=openharmony`, and
  `go version go1.27.1 openharmony/amd64` without GOOS/GOARCH environment overrides.
- Netgo and netcgo compile checks passed. Packed timezone tests passed for a
  valid entry, exact-name matching, reversed/oversized index bounds, malformed
  entry size, and oversized payload rejection.

These checks exercise code paths, not the OHOS customized libc, actual SDK
headers, CPU ABI on ARM64, sandbox policy, or a signed application lifecycle.

## CI-discovered cache regression

The initial PR CI bootstrap passed, but tests using the same cache as the
stock bootstrap compiler failed with export-data decoding panics. This was
reproduced locally by using the bootstrap cache. The fork originally reported
the same `go1.27.1` release tool identity as upstream. It now uses
`go1.27.1-hmos-devel`, so `-V=full` includes a content build ID, and CI also
separates bootstrap and test/SDK caches. This fix does not disable vet or
weaken tests.

## Blocked / never run

- Local SDK requests returned a 195-byte `Site Unavailable` HTML response;
  no substitute/fake sysroot was used. GitHub Actions run
  [37806744375](https://github.com/ZxillyFork/go-hmos/actions/runs/37806744375)
  subsequently downloaded the official 2.3 GB public SDK and verified its
  SHA-256, then failed during native-compiler discovery after extraction.
  The helper now follows valid LLVM clang symlinks and prints the actual
  layout if discovery still fails. That earlier run never reached linking.
  The successful exact-source SDK run recorded below supersedes this earlier
  download/discovery blocker. No device execution has occurred.
- Physical OpenHarmony/HarmonyOS NEXT device, x86_64 full-system emulator,
  signed HAP/N-API integration, native self-bootstrap, and complete target
  runtime/stdlib suites: **never run**.
- Target DNS/network-id behavior, certificate-service integration, system
  timezone-parameter synchronization, application permissions/signing,
  foreground/background lifecycle, and memory-pressure stress: **not verified**.
- The earlier hidden-stack metadata limitation is fixed in reviewed core
  `50a9db3`: AMD64 TLS expansion now has explicit PCSP/unsafe-point metadata,
  with independent emitted-object checks as well as regression-table coverage.
  Actual device unwinding and unwinding through the external TLS resolver
  remain unverified; host/compiler checks do not prove those behaviors. See the
  [current platform document](https://github.com/ZxillyFork/go-hmos/blob/50a9db343e53ec569374c328998b3ffbada8f850/doc/openharmony.md).

## Previous source pin: reviewed revision passed

Core commit
[`50a9db343e53ec569374c328998b3ffbada8f850`](https://github.com/ZxillyFork/go-hmos/commit/50a9db343e53ec569374c328998b3ffbada8f850)
passed all jobs in
[run 37819269863](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37819269863),
using build-repository commit `d305f22ce07c78d702d561f2f8567a972aa67584`.
The separate automatic host run
[37819196870](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37819196870)
also passed. This supersedes the earlier source results below for the default pin.

- Host bootstrap, compiler build IDs, shared-bootstrap-cache regression,
  platform/build-tag/codegen packages, API compatibility, command-driver check,
  and both target runtime Go/assembly builds passed.
- Host coverage includes `cmd/internal/buildid`, `cmd/internal/obj/arm64`, and
  `cmd/internal/obj/x86`: ELF-note, ARM64 TLS macro/stack, and AMD64
  PCSP/unsafe-point regressions are included.
- The official SDK archive again matched SHA-256
  `b833b75a64ee46bbd7880921abbb49b733ec5c8171b6684c9b524d57f624cee0`.
- ARM64 and AMD64 c-shared, c-archive, PIE, C loader, netgo shared-library,
  ELF architecture/TLS/stack/interpreter checks, six target standard-library
  test binary builds, and the target go/gofmt/compiler-tool builds passed.
- The SDK log records ARM64 PASS at 17:54:27 UTC and AMD64 PASS at 17:56:19 UTC
  on 2026-10-08, each explicitly stating `DEVICE EXECUTION NOT PERFORMED`.

The [final compile-only artifact](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37819269863/artifacts/11568603557)
is artifact `11568603557`: 66 files, 205,523,805-byte ZIP, SHA-256
`185d641428bce342e6eaaa3ca3827b49fe3d7640dcfa3fcb23f3450775ea956a`.
All 66 files were downloaded; both architecture source markers match the exact
core SHA, status files report exit 0/no device execution, and ELF reports were
inspected without executing target code. Its configured expiry is 2026-10-22.
It is not a supported release or complete installation. No target binary execution, real-device testing, emulator run,
HAP/N-API deployment, native self-bootstrap, or full target test-suite pass is
claimed. These results apply to this exact core revision only.

## Earlier independent-GOOS source

The earlier source was
[`fcaf70eef17b74d6acb8fd220d80edab8fdf3799`](https://github.com/ZxillyFork/go-hmos/commit/fcaf70eef17b74d6acb8fd220d80edab8fdf3799),
published with the independent `runtime.GOOS = "openharmony"` implementation.
The core no longer exports `runtime.IsOpenharmony`. Historical simulations above
were performed before that identity change and must not be attributed to the
new revision. In manual run
[37812418177](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37812418177),
the host/cache/codegen/API checks passed for this exact source. SDK download,
official SHA-256 verification, extraction, clang discovery, and both target C
compiler probes also passed. The verified SDK archive digest was
`b833b75a64ee46bbd7880921abbb49b733ec5c8171b6684c9b524d57f624cee0`.

Both architecture builds then failed before Go fixture compilation because the
wrapper supplied an absolute package directory in GOPATH mode. The wrapper now
builds `./library` and `./hello` from the fixture directory; a regression test
covers the actual working directory, arguments, and failure exit status. The
corrected run below subsequently established SDK cross-linking for this same
source revision. Device execution is still not performed.

## Passed with the official SDK on GitHub

[Run 37813650175](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37813650175)
completed successfully using build-repository commit
`31771e5823e7e82df3cbc94b6582bbbac55e8d3c` and core commit
`fcaf70eef17b74d6acb8fd220d80edab8fdf3799`. These results apply only to that core
revision; later review changes need their own validation.

- Host bootstrap, distinct compile/asm/link build-ID assertions,
  shared-bootstrap-cache regression, focused host/codegen tests, API check,
  command-driver check, and both target runtime Go/assembly builds passed.
- Official public OpenHarmony 6.1 SDK downloaded and matched SHA-256
  `b833b75a64ee46bbd7880921abbb49b733ec5c8171b6684c9b524d57f624cee0`.
  The compiler reports OHOS clang 15.0.4, LLVM revision
  `feef13a36e78b7a2ff3e9e3f180a958f2782be1e`.
- Both `aarch64-linux-ohos` and `x86_64-linux-ohos` passed c-shared, c-archive,
  PIE, C loader, and netgo shared-library compilation/linking.
- Real ELF inspection found the expected architecture, PT_TLS, TLSDESC
  relocations, a non-executable GNU_STACK, and the expected musl interpreter
  for PIE. Initial-exec TLS markers and TEXTREL were absent.
- Target test binaries compiled for runtime, os/signal, runtime/pprof, net,
  time, and crypto/x509. These tests were **not executed**.
- Target go, gofmt, asm, cgo, compile, cover, fix, link, preprofile, vet, and
  dist executables compiled. These tools were **not executed on the target**.
- Both architecture status files record `exit_status=0` and
  `device_execution=not_performed`. All 66 artifact files were downloaded and
  their source markers and ELF reports inspected without executing them.

[Compile-only artifact](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37813650175/artifacts/11566202919)
contains the binaries and reports; its configured expiry is 2026-10-22.
It is not a supported release or a complete install package. The automatic
host run [37813537193](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37813537193)
also passed for the same source pin. No device, simulator, HAP/N-API deployment,
native self-bootstrap, or complete target runtime/stdlib execution is established
by these results.

## Independent automation checks

The automation was moved into `ZxillyFork/go-hmos-build`, without adding a
workflow or installer to the Go core tree. Locally passed:

- Bash syntax checks for every shell helper.
- Twelve offline Python regression tests covering full-SHA input validation,
  compiler symlink discovery through real tar/zip extraction, checksum mismatch,
  invalid checksum responses, missing compilers, overwrite refusal, and missing
  SDK/unsupported-architecture rejection, valid job-level workflow contexts,
  and relative fixture import paths with preserved failure status.
- YAML parse, workflow structure inspection, and actionlint v1.7.7 validation.
- The complete `scripts/test-host.sh` run against the locally rebuilt
  cleanup/cache-fix worktree passed, including all three compiler build-ID
  assertions, focused packages, API check, command-driver test, and ARM64/AMD64
  runtime Go/assembly compilation. This predates the subsequent
  `runtime.GOOS = "openharmony"` identity change and is not a result for that
  later source revision. The local isolated bootstrap-cache directory was
  initially empty; the separate core validation owns the polluted-cache result.
  CI runs this regression after actually bootstrapping into that cache.

These offline tests are script checks, not SDK compilation. The separate real
SDK results are recorded above. The workflow records both architecture outcomes
independently and retains available diagnostics even when one fails. Each run
records the exact core SHA,
SDK URL, downloaded official checksum, compiler version, ELF evidence, and a
compile-only scope marker. The SDK checksum is obtained from the official
server during the run; it is not a historical digest pinned in this repository.

The first separate workflow run
[37810521458](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37810521458)
failed GitHub's workflow validation before any job began: `runner.temp` was
used in job-level `env`, where that context is unavailable. The workflow now
uses `github.workspace` for those ignored temporary directories, and an offline
regression test rejects unsupported job-environment contexts. The corrected run
[37811163764](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37811163764)
passed the offline checks. Its host and SDK jobs were intentionally skipped
because the default core pin was still unset at that point.

## Reproduce the real next validation stage

1. Check out the exact core SHA in `source.json`, set `GO_SOURCE_ROOT`, and run
   `scripts/bootstrap.sh` followed by `scripts/test-host.sh`.
2. Obtain the official public SDK and review its license. Set `OHOS_NDK_HOME`
   to its native directory and run
   `GOARCH=arm64 BUILD_NATIVE_TOOLS=1 bash scripts/build.sh`, then AMD64.
3. The opt-in **OpenHarmony build and checks → Run workflow → sdk=true** job in
   this repository runs the same checksum-verified SDK compilation/link/ELF
   checks. It accepts an explicit full core commit SHA. Its artifacts are named
   `openharmony-compile-only-<core-sha>`. Default host CI does not run SDK tests.
4. Sign/deploy as required by the selected OS/device and run the documented
   loader and standard-library tests. Only those results can establish actual
   target execution. Retain OS/API/SDK/build identifiers in the report.
