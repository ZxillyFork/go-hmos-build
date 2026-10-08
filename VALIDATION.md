# Validation record — 2026-10-08

This record distinguishes compilation, Linux-host ABI simulation, and real
OpenHarmony execution. **No OpenHarmony SDK-linked binary or actual device has
been executed for this change.** The port remains experimental and the core PR is a draft. This repository
contains build automation only; historical core results below do not establish
a passing run of the newly separated workflow.

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
  layout if discovery still fails. Real SDK linking remains unverified until
  the corrected job completes. No device execution has occurred.
- Physical OpenHarmony/HarmonyOS NEXT device, x86_64 full-system emulator,
  signed HAP/N-API integration, native self-bootstrap, and complete target
  runtime/stdlib suites: **never run**.
- Target DNS/network-id behavior, certificate-service integration, system
  timezone-parameter synchronization, application permissions/signing,
  foreground/background lifecycle, and memory-pressure stress: **not verified**.
- AMD64 TLS pseudo-instruction's interior PUSH/CALL/POP lacks independently
  represented PCSP metadata. Existing host tests are not an asynchronous
  unwind proof. See the [core platform document](https://github.com/ZxillyFork/go-hmos/blob/feature/openharmony-go1.27/doc/openharmony.md)
  for this and runtime restrictions.

## Current source pin

The initial build repository intentionally leaves `source.json` unpinned while
the independent `runtime.GOOS = "openharmony"` implementation is completed.
Default pushes run only offline helper tests; host/SDK builds are skipped,
not marked as validated. Manual dispatch requires an explicit reviewed full
`core_sha` until a final default pin is committed. No earlier intermediate
core SHA is silently selected.

## Independent automation checks

The automation was moved into `ZxillyFork/go-hmos-build`, without adding a
workflow or installer to the Go core tree. Locally passed:

- Bash syntax checks for every shell helper.
- Ten offline Python regression tests covering full-SHA input validation,
  compiler symlink discovery through real tar/zip extraction, checksum mismatch,
  invalid checksum responses, missing compilers, overwrite refusal, and missing
  SDK/unsupported-architecture rejection.
- YAML parse and workflow structure inspection.
- The complete `scripts/test-host.sh` run against the locally rebuilt
  cleanup/cache-fix worktree passed, including all three compiler build-ID
  assertions, focused packages, API check, command-driver test, and ARM64/AMD64
  runtime Go/assembly compilation. This predates the subsequent
  `runtime.GOOS = "openharmony"` identity change and is not a result for that
  later source revision. The local isolated bootstrap-cache directory was
  initially empty; the separate core validation owns the polluted-cache result.
  CI runs this regression after actually bootstrapping into that cache.

These are script checks, not SDK compilation. The workflow's actual SDK run must
still complete. It records both architecture outcomes independently and retains
available diagnostics even when one fails. Each run records the exact core SHA,
SDK URL, downloaded official checksum, compiler version, ELF evidence, and a
compile-only scope marker. The SDK checksum is obtained from the official
server during the run; it is not a historical digest pinned in this repository.

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
