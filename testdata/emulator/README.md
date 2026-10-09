# amd64 system-emulator fixtures

These bounded programs are intended to run inside a real HarmonyOS/OpenHarmony
amd64 system emulator. They reject any other `runtime.GOOS` or `runtime.GOARCH`.
They are not Linux userspace or QEMU-user substitutes for the target system.

- `emulator-native-probe`: a plain SDK C program with a pthread create/join
  check, run first to distinguish loader and libc issues from Go startup.
- `emulator-network-probe`: plain SDK C TCP/UDP loopback bind and getifaddrs
  checks, used to compare guest policy failures with the same operations in Go.
- `emulator-smoke`: Go identity; goroutines, channels, atomics, allocations and
  GC; stack growth and recoverable nil faults; timers and `LockOSThread`; temporary
  files; loopback TCP/UDP and interface enumeration; random bytes and SHA-256;
  authenticated TLS 1.2 and 1.3 over `net.Pipe` with a generated certificate.
- `emulator-cgo-smoke`: calls into C, concurrent locked-thread C TLS isolation,
  and 128 Go callbacks from four C-created pthreads, retaining C TLS across calls.
- `stdlib-tests.tsv`: the precise focused standard-library selections. The
  fields are package, artifact filename, anchored top-level test-name expression,
  and per-binary timeout in seconds. Comment lines start with `#`.

The `os/signal` selection tests context cancellation without sending reserved
signals: the port deliberately does not subscribe to or ignore signals 1–45.
The port-specific runtime and pprof selections verify that policy, recoverable
faults, heap profiling, and explicit rejection of unsupported CPU profiling.

No smoke check needs public DNS, internet connectivity, a system trust store, or
an external service. TLS uses an explicit local root and validation time. Socket
operations have deadlines. The executables also have watchdogs, but the host
runner must enforce an independent timeout in case target timers stop working.
Set `TMPDIR` to a writable directory in the guest before running them.
Independent smoke checks continue after a failure so a denied network operation
does not hide the crypto/TLS result. Failures still cause a nonzero exit. Each
dlopen variant runs once with the explicit `--no-network` option to isolate
runtime/ABI behavior, and again with mandatory interface discovery; the second
result is never discarded to obtain a green workflow.

Build with the actual SDK and the already bootstrapped source checkout:

```sh
GO_SOURCE_ROOT=/path/to/go-hmos OHOS_NDK_HOME=/path/to/sdk/native \
  GOARCH=amd64 OUT_DIR=/path/to/artifacts bash scripts/build-emulator-tests.sh
```

The build validates the SDK compiler's `__OHOS__` identity and each executable's
amd64 ELF, PIE type, musl interpreter, and non-executable stack. It rebuilds every
manifest package and copies the manifest only when all builds succeed. All test
binaries embed timezone data because upstream `time.test` initializes its test
timezone before test selection; the guest does not need a Go source tree. The
build status explicitly says device execution was not performed.

The runner must check exit status, require the exact smoke success marker, and
run every manifest row with `-test.v -test.short -test.count=1`, the exact
`-test.run` selection, and `-test.timeout=<seconds>s`. It must fail on empty test
selections, absent success output, or all-skipped groups, and record individual skips. A host compile or test
pass cannot be reported as an emulator pass.

## Host-only fixture checks

The Go `_test.go` files exercise fixture logic on the host without relaxing the
executables' target identity check:

```sh
GOROOT="$GO_SOURCE_ROOT" GO111MODULE=off GOTOOLCHAIN=local \
  "$GO_SOURCE_ROOT/bin/go" test -count=1 -timeout=120s \
  ./testdata/emulator/smoke ./testdata/emulator/cgo
python3 -m unittest discover -s testdata/emulator -p 'test_*.py' -v
```

These host checks are not target validation. A sandbox that denies netlink
interface enumeration fails `TestSmokeChecks/interfaces`; this does not weaken
or skip the guest check. To isolate unrelated host fixture logic, the exact
selection is `-run '^TestSmokeChecks$/(runtime|timers|files|tcp|udp|crypto|tls)$'`.

Copyright 2026 The Go Authors. All rights reserved. Use of this source code is
governed by the BSD-style license in the repository's LICENSE file.
