# Validation record — 2026-10-09

This record distinguishes compilation, Linux-host ABI simulation, and real
OpenHarmony execution. The official x64 emulator has now executed the pinned
Go runtime and focused tests. **The normal debug-HAP workflow passed all 20
app-process checks. The separate HDC-shell workflow remains failing because
network operations are denied in that context.** The port remains experimental;
this is not physical-device/release certification or a complete Go test suite. Historical
results below apply only to their stated exact source revisions.


## Normal app-process network validation

**Result: complete workflow SUCCESS; 20/20 app-process checks passed, none skipped.**
This is a separate experiment from the completed, failing HDC-shell test below.
The core pin remains `b637b8617624655906b737977f50de5280bf7f65`; no core change,
merge, release, physical device or ARM execution is part of this experiment.

The new `harmonyos-app-network.yml` workflow builds a normal Stage-model debug
HAP, `org.gohmos.networktest`, declaring only `ohos.permission.INTERNET`. A
small N-API worker loads one Go c-shared library. That library includes the
byte-for-byte pinned core `GoCheck` fixture and new same-process native C and Go
network controls. The build compares the fixture with the actual checked-out
core before compiling. It does not load two independent Go runtimes into one
process.

### Exact successful run and evidence

- [GitHub Actions run 37919648808](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37919648808),
  job `113784222807`, completed **success** on 2026-10-09 (10m04s).
- Tested build revision: `e3a7623d3f885ae59e2ab3fde9bea2aa936dc202`.
  Later documentation-only commits do not represent additional target runs.
- Unchanged core: `b637b8617624655906b737977f50de5280bf7f65`.
  Actual runtime: `go1.27.2-hmos-devel`, `GOOS=openharmony`, `GOARCH=amd64`.
- Official guest: OpenHarmony 6.1.1.125, API24, x86_64. Normal app bundle:
  `org.gohmos.networktest`; PID `3364`, UID/GID `20020049`.
  All C/Go rows report this same process; `/proc/3364/status` and cmdline
  independently match. Its actual SELinux context is `u:r:debug_hap:s0`,
  with effective capabilities zero. This is a **debug-app** result, not proof
  that a release-app security domain has the same access.
- Packed HAP is unsigned debug, declares only `ohos.permission.INTERNET`,
  and contains the two expected x86_64 libraries. SHA-256:
  `34a54ba4a9f03f37f9781508a82bcb09c5736b53353152713c02cea9e9592fed`.
- The [unaltered app report](validation/app-network-37919648808.json) is retained
  in this repository. SHA-256:
  `5e72f7dba44ce30e938b8b62e59e4d9576b9e2b2006ef1e8dab194ef11e08c5e`.
  Full HAP, packed permissions, process evidence, token-bearing hilog,
  screenshots and emulator logs are in the run's seven-day artifact.

| App-process checks | Result |
| --- | --- |
| Actual Go identity and pinned core `GoCheck(41)` | 2/2 PASS |
| C and Go raw TCP/UDP bind and UDP `SO_BROADCAST` | 6/6 PASS |
| C and Go TCP/UDP bidirectional IPv4 loopback exchange | 4/4 PASS |
| C `getifaddrs` and Go `net.Interfaces` | 2/2 PASS |
| Go addresses for lo, eth0, wifi_eth, sit0, wlan0 | 5/5 PASS |
| Canonical C/Go interface/address comparison | 1/1 PASS |

All rows have errno zero, no timeout and no failure. Five interfaces and nine
IPv4/IPv6 address/prefix entries matched; `sit0` correctly has no address.
Native IFF flags and Go net.Flags have different bit definitions and are not
claimed to match numerically. IPv6 **enumeration** passed; socket exchanges
were IPv4 loopback, not IPv6/public Internet/DNS tests.

The same previously denied shell operations succeeded in this normal debug
app process. This demonstrates that the earlier failures were context-specific,
not a general inability of the Go port to perform these operations. It does not
isolate INTERNET as the only causal difference between shell and debug-app policy.

The successful runner waited for BMS and then independently for UI evidence.
On its fourth UI attempt, a non-black welcome/clock screen and populated widget
tree were captured; ordinary `aa start` then succeeded. No Power key, swipe,
credential, lock/developer-mode/SELinux/network-policy change was needed.

Mandatory checks include:

- Actual `runtime.GOOS=openharmony`, `GOARCH=amd64`, app UID/PID, exact core pin
  and the original core `GoCheck` runtime smoke result.
- Matched raw C/libc and Go/syscall TCP/UDP loopback bind, using identical
  AF_INET, protocol zero and NONBLOCK/CLOEXEC socket flags.
- Matched `SOL_SOCKET/SO_BROADCAST=1` setup on a UDP socket.
- Bidirectional TCP and UDP loopback payload exchange. These are behavioral
  comparisons, not claims that the higher-level Go and C syscall sequences are
  identical.
- Native `getifaddrs`, Go `net.Interfaces`, per-interface addresses and address
  inventory comparison. INTERNET may still be insufficient for every operation;
  matched denials must be reported rather than skipped or granted more rights.

The runner checks the *packed* HAP's permission list, minimum API, debug flag
and x86_64 ELF library set. After normal ability launch, fresh random-token
hilog chunks carry a structured report; truncated, stale, missing and
inconsistent reports fail. Each test has a deadline, with a separate 180-second
host deadline. `/proc` identity must match the app report. Failed checks preserve
their stage and errno, and never turn into a successful overall workflow.

### Build and signing scope

- Same checksum-pinned official CLI 26.0.0.821 and reverified previously
  accepted agreements as the shell experiment. App building now uses its
  bundled HarmonyOS 26.0.0 ArkTS tools, with target/minimum `6.1.1(24)`.
- Native C and Go still cross-compile with the separate public OpenHarmony
  6.1/API23 SDK, and execution still targets the official API24 x64 image.
- No `signingConfig` is configured. Huawei's
  [introduction](https://developer.huawei.com/consumer/cn/develop-novice-guide/)
  states that emulator debugging does not require signing configuration, and
  its [build profile documentation](https://developer.huawei.com/consumer/cn/doc/doccenter-deveco-studio/ide-hmos-hvigor-build-profile-app)
  defines omitted signingConfig as unsigned. Ordinary unsigned installation
  succeeded on this exact API24 image in runs 37912008534, 37913592375 and
  37916270628 and the successful run 37919648808.
- An ordinary `hdc install` signature failure stops the experiment with its
  exact diagnostics. No account login, new signing key/profile, verifier bypass,
  SELinux change, additional app permission or guest root execution is used.

These are bounded app-startup and network probes. They do not establish
public Internet/DNS reachability, system trust roots, general lifecycle
correctness, release signing, app-store readiness or full Go suite coverage.

### Executed app-harness stages

The headless diagnostic run is [37913592375](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37913592375),
build revision `84500e6563cea5ef6d44141861d3969817387e1b`, overall **failure**.

- Exact pinned Go core bootstrap, six host Go fixture tests, target Go/C
  compilation, ArkTS compilation and normal debug HAP packaging passed.
- The packed HAP declares only INTERNET, is debug, contains only the two expected
  x86_64 libraries, and encodes minimum/target HarmonyOS 6.1.1 API24 as `60101024`.
- The official guest identifies as OpenHarmony 6.1.1.125/API24/x86_64.
  After BMS readiness, ordinary `hdc install` succeeded; the bundle has normal
  app UID `20020049`. This is install evidence, not an executed app identity.
- `aa start` reports error 10106102, screen locked, with automatic unlocking
  unavailable in developer mode. No developer-mode or lock-policy change was made.
- Both official `uitest screenCap` attempts failed to obtain a display pixelMap;
  layout capture timed out/failed. No actual screenshot or UI tree was produced.
- The engine's `qemu.log` first reports no GBM device, then surfaceless EGL 1.5,
  then `Failed to choose EGL config: 0x3000`. This is host graphics initialization
  evidence; it does not prove a password or a Go failure.

The preceding graphics run is [37916270628](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37916270628),
build revision `5cb80eb3c85314bc9132df5ecccad9903d4bb908`, overall **failure**.
It again passed all build/validation/ordinary-install stages. The host-only
Xvfb/Mesa change succeeded in initializing EGL 1.5, a matching EGL configuration
and llvmpipe OpenGL contexts. Both guest screenshots were successfully captured,
but visually inspected pixels were entirely black; widget-tree capture still
failed, and `aa start` still returned 10106102. No app-network report exists.
The final hilog shows SceneBoard creating desktop/dock/status-bar components
during teardown. Waiting for BMS alone was insufficient for a normal UI cold boot.
The successful revision adds a bounded, read-only UI-readiness wait; no Power
key, swipe, credential action or guest security change was introduced.

Earlier app runs are retained: 37908631884 exposed an overly strict bare-API24
validator assumption after successful packaging; 37910446087 attempted installation
before BMS was ready; 37912008534 first proved successful ordinary installation
and exposed the ability-launch blocker. None provided an app-network report.

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
general application lifecycle, release HAP/signing policy, public Internet/DNS,
system certificate policy and memory-pressure behavior remain unverified.
The bounded debug HAP/N-API integration and local app-network checks were
subsequently validated in the successful experiment above.

The shell failures motivated the normal x64 debug HAP experiment with only
[`ohos.permission.INTERNET`](https://github.com/openharmony/docs/blob/master/en/application-dev/security/AccessToken/permissions-for-all.md#ohospermissioninternet)
(normal, `system_grant`) declared in `module.json5`. A small
[N-API wrapper](https://github.com/openharmony/docs/blob/master/en/application-dev/napi/use-napi-process.md)
loads the pinned Go shared library in the actual app process and repeats
matched native C/Go network probes. An HDC shell launched from an app directory
is not equivalent to that application context. INTERNET does **not** guarantee
that every NETLINK_ROUTE operation or `getifaddrs` will be allowed.

The subsequent bounded debug-app experiment is recorded above: real build,
ordinary unsigned installation, app startup and all 20 focused checks passed.
Account-backed signing, new credentials/profiles or new legal terms are not
implied by the completed shell test.

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

## Linux SDK prerelease go1.27.2-hmos.1

- Build workflow: https://github.com/ZxillyFork/go-hmos-build/actions/runs/37922403510 — success
- Core merge: `7830d8769fefbe02c3b23d24f3d04bde6a1382da`; build: `9fa8ed40c031fa9ac431251fd23660082ab494f5`
- Release: https://github.com/ZxillyFork/go-hmos-build/releases/tag/go1.27.2-hmos.1
- Host: Linux/amd64; compiler identity: `go1.27.2-hmos-devel`
- Archive SHA-256: `04b5b24bcee3115be7cda879075c673245cd5655bb13c58261bea07b1bd4c072`

The exact merged source was bootstrapped and passed host/platform/API/security regressions.
The standard Go archive was loaded by the pinned official setup-go both before publication
and from the real release URL afterward. Fresh-cache source rebuilds cover generated
tzdata/buildcfg/cgo/compiler/Go-command sources. Both OpenHarmony target architectures
passed runtime code-generation checks and public-native-SDK PIE/c-shared linking with
ELF/TLS inspection. Published archive/provenance checksums were verified in CI and by a
separate download; the selected fork identity and embedded source SHA were checked.

This SDK run does not execute binaries on a target device. No native SDK is redistributed.
[Retained verification record](validation/linux-sdk-37922403510.json) and
[setup-go integration](docs/linux-sdk.md) describe the complete contract and remaining limits.

## HDC shell DNS/TCP/HTTPS validation for go1.27.2-hmos.4

Core: `e6f73c93079c6bc3c41086632420af33bb3de631`. On 2026-10-10,
manual probes ran in the official HarmonyOS 6.1.1 x64/API24 emulator under
WSL Ubuntu/KVM. The guest reported `OpenHarmony-6.1.1.125`; execution used
HDC shell uid 2000 (`u:r:sh:s0`) with SELinux Enforcing unchanged.

The original source failed UDP DNS at `SO_BROADCAST` and TCP connections at
`SO_ERROR`, both with permission denied. Native C controls confirmed that
unicast UDP and TCP connections themselves were allowed. The fixes ignore
only OpenHarmony datagram broadcast-option EACCES/EPERM and, when SO_ERROR
is denied, accept a connection only after getpeername verifies a peer.

Patched-source target execution passed:

- UDP DNS and forced TCP DNS through the system-selected resolver (10.0.2.3).
- Direct TCP and HTTPS to example.com, including response-body consumption.
- Default x509 system pool loading (125 roots) and verified HTTPS chains,
  without SSL_CERT_FILE, SSL_CERT_DIR, supplied certificates or disabled TLS checks.
- Closed-port connections still fail; pre-canceled contexts still return cancellation.
- The original cjv command `toolchain list-remote --channel nightly --limit 1 --json`
  returned nightly metadata successfully. HOME was set to a dedicated writable
  directory because cjv requires it; the returned platform version list was empty.
- Local time Asia/Shanghai, explicit Shanghai/Berlin/New_York zones, temporary
  file creation, shell user lookup and PDF/DOCX MIME lookup.

The existing Linux net and crypto/x509 short suites passed. OpenHarmony ARM64
cross-compilation passed, but ARM64 device execution was not performed. No new
regression test files were added; these were manual external probes.

Remaining boundary: net.Interfaces still fails while creating a route socket in
this shell domain. Bind/listen is also restricted. These results do not establish
arbitrary device or app permissions. Missing /etc/localtime is expected and is
handled by the existing platform timezone implementation.

Related primary references:

- [Huawei's default CA path](https://developer.huawei.com/consumer/en/doc/harmonyos-faqs-V14/faqs-network-41-V14)
  is `/etc/ssl/certs/cacert.pem`. The shell can read it even though it cannot
  enumerate `/etc/security/certificates`; the latter remains a fallback.
- [OpenHarmony NDK network guidance](https://github.com/openharmony/docs/blob/master/zh-cn/application-dev/napi/c-cpp-overview.md#网络使用)
  recommends ioctl instead of RTM_GETLINK for interface queries. This does not
  guarantee that a shell domain may create a route socket.
- [iana-time-zone's OpenHarmony implementation](https://github.com/strawlab/iana-time-zone/blob/main/src/tz_ohos.rs)
  also handles the absence of /etc/localtime through a platform-specific path.
Published hmos.4 verification:

- [CI run 38014707642](https://github.com/ZxillyFork/go-hmos-build/actions/runs/38014707642)
  completed successfully, including host checks, both target architectures,
  native PIE/c-shared links, and official setup-go before and after publication.
- Build commit: `aa2bdb3d864b8e079a46eddbf10932083e95a068`.
- [Release](https://github.com/ZxillyFork/go-hmos-build/releases/tag/go1.27.2-hmos.4)
  archive SHA-256: `50926cf754c544b6cbe230fad4088d13be310d923adcb35247237e0c208af971`.
- An independent download verified archive/provenance hashes, the manifest,
  embedded core revision, and compiler identity. The downloaded SDK compiled
  both the network probe and cjv successfully.
- A second emulator execution attempt using those release-built binaries was
  blocked by HDC transfer timeout and subsequent target disconnection, including
  after restarting the HDC server. The successful target execution above used
  the same core source changes with the local compiler; release-built target
  execution is not claimed. The dedicated test emulator was stopped afterward.

## Signal 64 exec regression validation for go1.27.2-hmos.5

Core: `7ea2c37368c408d68804c9bda8f9e74b03fe4122`.
On 2026-10-10, the OpenHarmony ARM64 runtime was tested with the experimental
headless startup of the HarmonyOS 6.1.1 ARM64 PC image under x86 QEMU/TCG.
The guest reported OpenHarmony 6.1.1.125, HDC shell uid 2000 and SELinux
Enforcing. This is not a graphical emulator or real PC HiShell validation.

- Before the repair, a minimal Go program replacing itself with the native
  system shell via `syscall.Exec` failed with signal 64 in 13 of 30 attempts.
- After the repair, the same stress test passed all 30 attempts.
- `syscall.TestOpenHarmonyExecPreemption` passed all 60 child invocations,
  covering successful exec, repeated failed exec and locked-thread exits.
- Target runtime policy, synchronous-fault, preemption, GC-preemption and
  post-syscall preemption tests passed; the `AsyncPreempt` helper returned OK.
- Cjv built from source `cf9975edd7c5ea96e35554e43861fe34d8c0c87f` with the
  repaired runtime downloaded and installed the actual online nightly
  `1.3.0-alpha.20261010001050`. Its default `cjc --version` proxy passed 20/20
  invocations with GODEBUG unset. Default-proxy compilation and program
  execution printed `CJV_LIVE_INSTALL_NIGHTLY_OK`.
- Focused Linux host preemption/exec tests passed. OpenHarmony amd64 syscall
  tests and Darwin arm64 runtime tests cross-compiled; they were not executed.

These runtime results used locally built binaries from the exact repaired
source. They do not yet establish execution of the separately published SDK
bytes. The versioned release workflow records package, host, cross-link and
post-publication verification for the new distribution.

Published hmos.5 verification:

- Release workflow `38033062342` passed both packaging and post-publication
  verification at build commit `6e06ab5137ed38091b1e0f7a08da1786acc758ce`.
- The downloaded archive SHA-256 matched `SHA256SUMS`, the release manifest and
  GitHub's asset digest:
  `a98f1668e44b5f5e3d982f0a3287bc412a2b1c3c9ce356ec3ef82de3abd3cf14`.
- The published archive's core revision matched
  `7ea2c37368c408d68804c9bda8f9e74b03fe4122`; its three repaired runtime source
  files and new syscall regression test matched that commit byte for byte.
- Using only the extracted published SDK, the ARM64 syscall test binary was
  rebuilt and executed in the same headless OpenHarmony 6.1.1.125 environment.
  `TestOpenHarmonyExecPreemption` passed all three cases (60 child invocations)
  in 67.66 seconds with guest exit code 0. A second device-log check also passed
  all three cases in 49.97 seconds. Asynchronous preemption remained enabled.
- The temporary ARM64 VM was stopped and its RAM overlays and build cache were
  removed. This confirms target execution from the published SDK; it does not
  establish real PC HiShell behavior or native cgo execution.
