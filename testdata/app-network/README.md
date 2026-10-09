# Same-process app network fixture

This directory builds **one** Go `c-shared` library. The app's native N-API host
loads it once and calls `GoAppNetworkCheck`. Native libc checks are invoked by cgo
in that same process. Do not load a second Go shared library or `dlclose` this one.

## C ABI

- `char *GoAppNetworkCheck(void)`: allocated NUL-terminated JSON report
- `void GoAppNetworkFree(char *)`: release that report after the host copies it
- `int GoCheck(int)` and `int GoNetworkCheck(void)`: original pinned core exports

Set `OHOS_GO_TEST=before-dlopen` in the native host **before loading the library**.
Run the network export in the N-API async worker, rather than the UI thread.
`GoAppNetworkCheck` itself calls `GoCheck(41)` and expects return code **0**.

The report has `schema_version: 1`, `core_revision`, `overall_pass`, `identity`
(`goos`, `goarch`, `version`, `pid`, `uid`, `gid`), `checks`, and `failed`.
Each check records `name`, `implementation`, `operation`, `stage`, `passed`,
`errno`, `error`, `timed_out`, `duration_ms`, and its own `process` identity.
An `errno` of zero can mean a non-OS error, panic, or outer deadline; inspect
`error`, `stage`, and `timed_out` too. The report is still returned when checks
fail. Never infer success merely because the export returned normally.

Required stable names:

```
identity
core.GoCheck
native.raw_tcp_bind
go.raw_tcp_bind
native.raw_udp_bind
go.raw_udp_bind
native.raw_udp_broadcast
go.raw_udp_broadcast
native.tcp_roundtrip
go.tcp_roundtrip
native.udp_roundtrip
go.udp_roundtrip
native.getifaddrs
go.net_interfaces
interfaces.addresses_match
```

Successful `net.Interfaces` enumeration adds one
`go.interface_addrs:<interface name>` check per interface. Native interface rows
and Go per-interface address rows are included in their respective checks.
The comparison canonicalizes addresses and prefix lengths, deduplicates rows,
and sorts by interface name/address. Flags are reported without incorrectly
equating native `IFF_*` bits and Go `net.Flags` bits. Sequential snapshots can
legitimately differ when the device's interfaces change; such a mismatch is a
failure with both sets preserved for diagnosis.

## What is actually compared

Raw native/Go syscall pairs both use `AF_INET`, protocol zero, and identical
`SOCK_NONBLOCK | SOCK_CLOEXEC` flags. Raw bind uses `127.0.0.1:0` without any prior
socket options. The independent UDP option check uses
`setsockopt(SOL_SOCKET, SO_BROADCAST, 1)` on a fresh identically flagged socket.
Both the numeric inputs and exact failed stage are recorded.

Native TCP and UDP round trips use libc sockets, nonblocking I/O, and `poll`.
Go TCP and UDP round trips use `net`. Each exchanges and verifies a payload in
both directions, including an embedded NUL byte. These are **behavioral**
comparisons: `net` may enable additional socket options, including UDP
`SO_BROADCAST`, so a bare C bind passing does not establish a Go regression.

Each round trip has one 3-second absolute socket deadline. Each independent
check has a 5-second outer Go deadline, including `getifaddrs` and interface
queries. A timed-out worker cannot mutate the returned report, but a libc/kernel
call may remain blocked until process termination. The external app runner
must impose an additional deadline in case the runtime or its timers fail.
Only the external runner may decide whether app-context evidence is valid.

## Pinned smoke fixture provenance

`core_smoke.go` is a byte-for-byte copy of:

https://github.com/ZxillyFork/go-hmos/blob/b637b8617624655906b737977f50de5280bf7f65/src/cmd/cgo/internal/testcshared/testdata/openharmony/library/main.go

- Core revision: `b637b8617624655906b737977f50de5280bf7f65`
- Git blob: `8ff725cfcc7eab8282361a75e24d101c0af1f16c`
- SHA-256: `5785013b6ca9e3b11231fc9760a4c3c97ccc2c2e8d3295d7c85b9f64e7fed1b4`

The build wrapper compares this copy with the pinned checkout before compiling.
This keeps the original smoke entry points and the new checks within one Go
runtime without modifying the core repository.

## Host-only tests

```
python3 testdata/app-network/test_native.py -v
GO111MODULE=off CGO_ENABLED=1 go test -count=1 ./testdata/app-network
```

Use a Go version supporting `sync.WaitGroup.Go` for the copied core fixture.
Native host tests verify repeated TCP/UDP exchanges, identical socket flags and
process identity, plus injected bind/setsockopt/getifaddrs errors and poll
timeouts. A host sandbox that denies `getifaddrs` produces an explicit skipped
host-interface test. Target app checks **never** turn such errors into skips.
Go tests cover the raw pair arguments, loopback exchanges, JSON contract,
address comparison, wrapped errno, panic isolation, and the outer deadline.
Host execution intentionally fails target identity and core smoke checks in
the complete JSON report; it cannot claim `openharmony/amd64` validation.
