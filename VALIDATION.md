# Validation record — 2026-10-09

This record distinguishes compilation, Linux-host ABI simulation, and real
OpenHarmony execution. The official x64 emulator has now executed the pinned
Go runtime and focused tests. **The full emulator workflow remains failing:
network checks are denied in the HDC shell context.** The port remains
experimental; this is not physical-device certification, a complete Go test
suite, or validation of networking in an application context. Historical
results below apply only to their stated exact source revisions.


## Official x64 emulator runtime validation

**Result: the experimental Go runtime and native-library ABI execute on the
official x64 emulator. The complete workflow is not green: network operations
are restricted in its HDC shell context. ARM was not tested.**

The final same-operation C/Go comparison is
[run 37884563219](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37884563219),
which completed with `failure` at the mandatory network checks. Its exact
executable test code is build commit
[`efa924f1b10e55cc26d8026a6768a2b3130e0336`](https://github.com/ZxillyFork/go-hmos-build/commit/efa924f1b10e55cc26d8026a6768a2b3130e0336),
using unchanged core
[`b637b8617624655906b737977f50de5280bf7f65`](https://github.com/ZxillyFork/go-hmos/commit/b637b8617624655906b737977f50de5280bf7f65).
The later documentation-only commit does not alter this tested code and skips
CI to avoid repeating known shell-policy failures.

### Environment and provenance

- GitHub-hosted Ubuntu 24.04 x64; real KVM API 12 and `KVM_CREATE_VM` succeeded.
  The test process runs as the runner user with a temporary KVM group; no
  device ACL, group membership, SELinux, or other system-policy changes.
- Official Huawei Command Line Tools 26.0.0.821, archive SHA-256
  `58da7359019e9360a8bb82da0cd1d3b3b26fedc338379f257849f2162e3ac1fc`.
  The exact package and all four emitted agreement texts were compared with
  the previously accepted [cjv run 37875586125](https://github.com/Zxilly/cjv/actions/runs/37875586125).
  Source and agreement hashes are in `scripts/emulator/`; no new or changed
  terms are accepted automatically.
- Official CLI-installed HarmonyOS 6.1.1 (API 24) PC image; the guest reports
  `OpenHarmony-6.1.1.125`, API `24`, `x86_64`, Linux `5.10.210`.
  `system.img` is 3,250,585,600 bytes, SHA-256
  `12dfd14d80234783750a14d7768bc73daed4f5d17e77152a2e00f70523dbec15`.
- Compilation uses the separate public OpenHarmony 6.1/API 23 SDK. Its official
  downloaded archive checksum is
  `b833b75a64ee46bbd7880921abbb49b733ec5c8171b6684c9b524d57f624cee0`.
  The compiler target, sysroot, ELF machine, PIE type and interpreter are
  checked before transfer. Compilation SDK and execution image are not
  presented as the same distribution/version.
- Guest execution is through HDC as UID/GID 2000 (`shell`), SELinux context
  `u:r:sh:s0`. Per-file hashes and randomized guest exit markers prevent an
  HDC zero exit status from being mistaken for a successful guest command.

### Actually executed and passed

- Plain SDK C loader/libc/pthread create/join probe and actual Go hello:
  `openharmony/amd64 (runtime.GOOS=openharmony)`.
- Goroutines, channels, atomics, allocations/GC, stack growth, recoverable nil
  faults, timers, locked OS threads, and temporary-file operations.
- Random bytes/SHA-256 and authenticated TLS 1.2 and 1.3 over in-memory
  `net.Pipe`. This TLS check does not establish TCP networking or system roots.
- Cgo calls, C thread-local storage isolation, and 128 Go callbacks from four
  foreign pthreads.
- Both ordinary and `netgo` Go shared libraries loaded with `dlopen`. The
  explicitly isolated `--no-network` runs each pass 100 foreign-pthread
  callbacks, environment access, GC, goroutines, timers, panic recovery and
  reserved-signal-handler preservation. The full network-enabled runs are
  also executed and remain failing; their outcomes are not replaced by the
  isolated results.
- 18 standard-library packages: **130 selected top-level tests passed**, zero
  missing selections, and **one explicit skip**,
  `compress/flate.TestDeflateInflateString` (upstream skips it in `-test.short`
  mode). The exact 131 selections are in `testdata/emulator/stdlib-tests.tsv`.
  This includes port-policy/fault tests, heap profiling and the expected
  rejection of unsupported CPU profiling; it is not full profiling support.
- Simulator log collection and stop completed successfully. Logs and test
  payloads are attached to the run; SDK/CLI/system images are not uploaded.

### Network failures and the native C control

The native probe uses the same SDK libc and the same HDC shell identity:

- TCP loopback bind: native C returns `errno=13` (`EACCES`), and Go reports
  `bind: permission denied`.
- Bare native UDP loopback bind succeeds. Go's UDP setup first enables
  `SOL_SOCKET/SO_BROADCAST`, so bare bind was not a complete comparison.
  The final native probe repeats Go's nonblocking/close-on-exec socket flags
  and the same `SO_BROADCAST=1` option: **that C call also returns EACCES**.
  Go reports `setsockopt: permission denied` at that operation.
- Native `getifaddrs` returns EACCES, as do Go `net.Interfaces` and both shared
  library variants. `netgo` still uses the port's libc interface-discovery
  implementation; it is not a separate pure-Go enumeration control.

These matched C/Go denials establish that the observed failures are not
specific to Go's runtime or ABI implementation. They are a networking
restriction of the tested shell execution context; the tests do not identify
which exact security layer imposed every denial. The existing official
[shell TCP policy](https://github.com/openharmony/security_selinux_adapter/blob/b8cc1cb5ab75f246b7ec0d8a5ef047b7c69e8c65/sepolicy/ohos_policy/liteos/toybox/public/sh.te)
and [HDC shell policy](https://github.com/openharmony/security_selinux_adapter/blob/b8cc1cb5ab75f246b7ec0d8a5ef047b7c69e8c65/sepolicy/ohos_policy/developtools/hdc/system/sh.te)
are consistent with restricted socket operations, but are not claimed to be
an exact policy dump of this commercial emulator image.

The workflow deliberately remains failing on these mandatory network checks.
No core patch, permission expansion, privileged execution inside the guest,
or policy relaxation was used to obtain a passing subset.

### Remaining validation and next context

Physical ARM devices, full Go/stdlib suites, native toolchain self-bootstrap,
application lifecycle, signing/HAP/N-API integration, real application
networking, DNS, system certificate policy and memory-pressure behavior remain
unverified.

A bounded next experiment would be a normal x64 debug HAP with only
[`ohos.permission.INTERNET`](https://github.com/openharmony/docs/blob/master/en/application-dev/security/AccessToken/permissions-for-all.md#ohospermissioninternet)
(normal, `system_grant`) declared in `module.json5`. A small
[N-API wrapper](https://github.com/openharmony/docs/blob/master/en/application-dev/napi/use-napi-process.md)
would load the existing Go shared library in the actual app process and repeat
matched native C/Go network probes. An HDC shell launched from an app directory
is not equivalent to that application context. INTERNET does **not** guarantee
that every NETLINK_ROUTE operation or `getifaddrs` will be allowed.

That app-context build/install/run has not been performed. The official
emulator-debug signing route must be checked before deciding whether account
credentials are needed; unsigned or arbitrary self-signed HAP acceptance is
not assumed. Account-backed signing, new credentials/profiles or new legal
terms are not implied by the completed shell test.

### Harness validation and initial failures

The final harness passed 56 local offline Python checks (52 runner/license
checks plus four build-fixture checks), Bash syntax, Go formatting, host C
syntax checks and actionlint. These are not target-execution evidence.

Initial runs fixed a runner `sudo` invocation and a conservative license-view
parser before target execution. One real image download reached 77.0% of
2,352,917,078 bytes in 20 minutes without errors; its timeout was therefore
raised to 40 minutes, with a 90-minute job limit and streamed progress. This
was a download-stage timeout, not an emulator or Go failure. The first actual
execution in [run 37882584125](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37882584125)
and the first native network control in
[run 37883765934](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37883765934)
are retained separately from the final same-operation control above.

## Go 1.27.2: host and official SDK verified

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

Local checks on the new exact core revision passed:

- Complete Linux/amd64 three-stage bootstrap, distinct compile/asm/link build
  IDs, shared-bootstrap-cache regression, platform/build-tag/codegen tests,
  API compatibility, and the OpenHarmony command-driver test.
- Full `net/textproto`, `net/http`, `net/http/httputil`,
  `net/http/internal/http2`, and `mime/multipart` suites.
- All seven ECH outer-extension cases, selected `os.Root` regressions,
  race-enabled HTTP/2 header-table update regression, and ARM64/AMD64 runtime
  Go/assembly compilation.
- Actual Linux installation into a path with spaces, cached reinstall,
  exact version, host smoke, installed-fork `os.Root` regressions, and launcher
  behavior. Installer unit tests and vet also passed with both official
  Go 1.27.2 and the minimum Go 1.24.6.
- Thirteen offline helper tests, Bash syntax, YAML parsing, actionlint v1.7.7,
  and independent review of the merge, branch ancestry, pins, and test harness.

The local full `crypto/tls` suite failed only `TestVerifyHostname` and
`TestRealResumption`: direct DNS for their external google/yahoo connections
is blocked by this environment. These tests remain enabled for CI; the local
suite is not recorded as a complete pass. The local official SDK checksum
request returned a 195-byte invalid response, so no substitute SDK was used.

### Exact-source GitHub validation

Core `b637b8617624655906b737977f50de5280bf7f65`, built using repository revision
`4763ded31827005420d317bae2881c958b4e321d`, passed all jobs in
[host + official SDK run 37872123883](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37872123883).
[Automatic host run 37871812524](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37871812524)
also passed on rerun. Its first attempt stopped during source checkout before
the new core revision was available; no build/test result was claimed for that
attempt.

- Full host security-package suites, including the two external-network TLS
  tests blocked locally, passed with Go 1.27 defaults. Bootstrap, build/cache
  identities, focused platform/codegen/API/driver checks, the selected
  `os.Root` tests, HTTP/2 race regression, and both target runtime builds passed.
- The official OpenHarmony 6.1 SDK archive matched SHA-256
  `b833b75a64ee46bbd7880921abbb49b733ec5c8171b6684c9b524d57f624cee0`,
  identical to the previously validated 6.1.0.31 / API 23 archive. Its compiler
  is OHOS clang 15.0.4, LLVM revision
  `feef13a36e78b7a2ff3e9e3f180a958f2782be1e`.
- ARM64 and AMD64 passed c-shared, c-archive, PIE, C loader, netgo library,
  six target standard-library test-binary builds, and native Go-tool builds.
  ELF checks confirmed the architecture, PT_TLS/TLSDESC, non-executable stack,
  expected musl interpreter, PIE, and absence of initial-exec TLS/TEXTREL.
- The SDK log records ARM64 PASS at 02:03:04 UTC and AMD64 PASS at 02:04:56 UTC
  on 2026-10-09, explicitly as compile/link/ELF checks only.

[Compile-only artifact 11590408485](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37872123883/artifacts/11590408485)
contains 66 files, 205,530,590 bytes; ZIP SHA-256 is
`a1e55205697e8255d6e2114ec6b17f9a6dbd188e7e1a2e63bee0a61c59c7389b`.
The downloaded ZIP digest was verified, and both architecture source markers,
status files, toolchain version, target environment, expected outputs, and ELF
reports were inspected. Both source markers match the exact core SHA and both
status files record exit 0 / device execution not performed. The artifact's
configured expiry is 2026-10-23; it is not a release or complete installation.

### Versioned installer

Installer commit
[`e33a5258fba55916b9aef00c9df8e4de45a0bdfd`](https://github.com/ZxillyFork/go-hmos-installer/commit/e33a5258fba55916b9aef00c9df8e4de45a0bdfd)
provides the explicit `go1.27.2-hmos` command, fixed to the new core revision:

```sh
go install github.com/ZxillyFork/go-hmos-installer/go1.27.2-hmos@latest
go1.27.2-hmos download
go1.27.2-hmos version
```

The toolchain still identifies itself as `go1.27.2-hmos-devel`; this is a
reviewed experimental snapshot, not a release tag or prebuilt distribution.
Its SDK remains in `~/sdk/go1.27.2-hmos`, while the official `go1.27.2` helper
and SDK can coexist. The legacy installer root retains source
`50a9db343e53ec569374c328998b3ffbada8f850` and its original selection/CLI;
installing the versioned command does not upgrade that legacy entry.

All four jobs passed in
[final installer run 37876369615](https://github.com/ZxillyFork/go-hmos-installer/actions/runs/37876369615):

- Native Linux, macOS, and Windows: unit tests/vet, genuine official-helper
  coexistence with unchanged binary hash, fresh legacy and new-version source
  builds, paths with spaces, relocation, cached reinstall, host smoke,
  environment forwarding, and installed-toolchain security regressions.
- Windows: the new source's dangling-junction `os.Root` cases were required
  to pass explicitly; skipped tests do not satisfy the assertions.
- Minimum Go 1.24.6: installer unit tests and vet. This job does not claim a
  full source bootstrap using the minimum compiler.

The earlier interim `go1.27.2` package collided with the official helper name;
the final module removes it and uses only `go1.27.2-hmos`. Historical module
revisions are unchanged, and no existing user launcher is automatically
removed. The installer's README explains how users can inspect or manually
restore an old same-name launcher. The earlier run on `aaa18b9` is not used as
final-SHA verification.

The final module was retrieved through the public Go proxy with the checksum
database enabled as `v0.0.0-20261009024803-e33a5258fba5`, with module checksum
`h1:4TsEZhvyTy7vKVckDMgRp9nXbhQRGuPNfOrPNDWuZQo=` and verified origin SHA
`e33a5258fba55916b9aef00c9df8e4de45a0bdfd`. Mutable `@latest` metadata may lag
publication while mirrors refresh; use a reviewed full installer SHA for a
reproducible launcher version.

No target device, emulator, HAP/N-API deployment, native self-bootstrap, or
complete target runtime/stdlib execution is established by these results.

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
