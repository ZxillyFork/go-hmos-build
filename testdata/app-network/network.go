// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

package main

/*
#include "native.h"
#include <stdlib.h>
#include <sys/socket.h>
*/
import "C"

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"runtime"
	"sort"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const operationTimeout = 3 * time.Second
const checkTimeout = 5 * time.Second

const coreRevision = "4f16eff34baee504014f56bd8b7148293f85362a"

type processIdentity struct {
	PID int `json:"pid"`
	UID int `json:"uid"`
	GID int `json:"gid"`
}

type interfaceAddress struct {
	Name string `json:"name"`
	Address string `json:"address,omitempty"`
	Family int `json:"family"`
	PrefixLength int `json:"prefix_length"`
	Flags uint32 `json:"flags"`
}

type checkResult struct {
	Name string `json:"name"`
	Implementation string `json:"implementation"`
	Operation string `json:"operation"`
	Stage string `json:"stage"`
	Passed bool `json:"passed"`
	Errno int `json:"errno"`
	Error string `json:"error"`
	TimedOut bool `json:"timed_out"`
	DurationMS int64 `json:"duration_ms"`
	Process processIdentity `json:"process"`
	Details map[string]any `json:"details,omitempty"`
	Interfaces []interfaceAddress `json:"interfaces,omitempty"`
}

type report struct {
	SchemaVersion int `json:"schema_version"`
	OverallPass bool `json:"overall_pass"`
	CoreRevision string `json:"core_revision"`
	Identity struct {
		GOOS string `json:"goos"`
		GOARCH string `json:"goarch"`
		Version string `json:"version"`
		processIdentity
	} `json:"identity"`
	Checks []checkResult `json:"checks"`
	Failed []string `json:"failed"`
	Notes []string `json:"notes"`
}

func currentProcess() processIdentity {
	return processIdentity{PID: os.Getpid(), UID: os.Getuid(), GID: os.Getgid()}
}

func newResult(name, implementation, operation string) checkResult {
	return checkResult{Name: name, Implementation: implementation, Operation: operation,
		Stage: "complete", Passed: true, Process: currentProcess()}
}

func failure(r checkResult, stage string, err error) checkResult {
	r.Passed = false
	r.Stage = stage
	r.Error = err.Error()
	var errno syscall.Errno
	if errors.As(err, &errno) {
		r.Errno = int(errno)
	}
	var netError net.Error
	r.TimedOut = errors.Is(err, os.ErrDeadlineExceeded) || errors.Is(err, syscall.ETIMEDOUT) ||
		(errors.As(err, &netError) && netError.Timeout())
	return r
}

// A kernel/libc stall is reported as failure without preventing independent
// checks from running. A timed-out worker owns all of its resources until it
// returns and never mutates the report. The app runner must additionally impose
// an external deadline in case Go timers or the runtime itself fail.
func bounded(name, implementation, operation string, run func() checkResult) checkResult {
	start := time.Now()
	result := make(chan checkResult, 1)
	go func() {
		defer func() {
			if value := recover(); value != nil {
				result <- failure(newResult(name, implementation, operation), "panic", fmt.Errorf("%v", value))
			}
		}()
		result <- run()
	}()
	timer := time.NewTimer(checkTimeout)
	defer timer.Stop()
	var r checkResult
	select {
	case r = <-result:
	case <-timer.C:
		r = failure(newResult(name, implementation, operation), "check deadline", os.ErrDeadlineExceeded)
	}
	r.DurationMS = time.Since(start).Milliseconds()
	return r
}

func rawDetails(socketType int) map[string]any {
	return map[string]any{
		"address_family": syscall.AF_INET, "socket_type": socketType,
		"socket_flags": syscall.SOCK_NONBLOCK | syscall.SOCK_CLOEXEC, "protocol": 0,
		"address": "127.0.0.1", "port": 0,
	}
}

func nativeCheck(name, operation string, nativeOperation C.int) checkResult {
	r := newResult(name, "native-libc", operation)
	value := C.app_network_run(nativeOperation, C.int(operationTimeout.Milliseconds()))
	if value == nil {
		return failure(r, "native result allocation", syscall.ENOMEM)
	}
	defer C.app_network_result_free(value)
	r.Passed = value.passed != 0
	r.Errno = int(value.error_number)
	r.Error = C.GoString(&value.error_text[0])
	r.Stage = C.GoString(&value.stage[0])
	r.TimedOut = r.Errno == int(syscall.ETIMEDOUT)
	r.Process = processIdentity{PID: int(value.pid), UID: int(value.uid), GID: int(value.gid)}
	if nativeOperation <= C.APP_RAW_UDP_BROADCAST {
		socketType := int(C.SOCK_DGRAM)
		if nativeOperation == C.APP_RAW_TCP_BIND {
			socketType = int(C.SOCK_STREAM)
		}
		r.Details = rawDetails(socketType)
		r.Details["address_family"] = int(C.AF_INET)
		r.Details["socket_flags"] = int(value.socket_flags)
		if nativeOperation == C.APP_RAW_UDP_BROADCAST {
			delete(r.Details, "address")
			delete(r.Details, "port")
			r.Details["level"] = int(C.SOL_SOCKET)
			r.Details["option"] = int(C.SO_BROADCAST)
			r.Details["value"] = 1
		}
	}
	for _, item := range unsafe.Slice(value.interfaces, int(value.interface_count)) {
		r.Interfaces = append(r.Interfaces, interfaceAddress{
			Name: C.GoString(&item.name[0]), Address: C.GoString(&item.address[0]),
			Family: int(item.family), PrefixLength: int(item.prefix_length), Flags: uint32(item.flags),
		})
	}
	if r.Process != currentProcess() {
		return failure(r, "same-process identity", fmt.Errorf("native identity %+v differs from Go %+v", r.Process, currentProcess()))
	}
	return r
}

func goRawBind(name string, socketType int) checkResult {
	r := newResult(name, "go-syscall", "socket(AF_INET,type|SOCK_NONBLOCK|SOCK_CLOEXEC,0); bind(127.0.0.1:0)")
	r.Details = rawDetails(socketType)
	fd, err := syscall.Socket(syscall.AF_INET, socketType | syscall.SOCK_NONBLOCK | syscall.SOCK_CLOEXEC, 0)
	if err != nil {
		return failure(r, "socket", err)
	}
	defer syscall.Close(fd)
	if err := syscall.Bind(fd, &syscall.SockaddrInet4{Addr: [4]byte{127, 0, 0, 1}}); err != nil {
		return failure(r, "bind(127.0.0.1:0)", err)
	}
	return r
}

func goRawBroadcast() checkResult {
	r := newResult("go.raw_udp_broadcast", "go-syscall", "socket(AF_INET,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0); setsockopt(SOL_SOCKET,SO_BROADCAST,1)")
	r.Details = rawDetails(syscall.SOCK_DGRAM)
	delete(r.Details, "address")
	delete(r.Details, "port")
	r.Details["level"] = syscall.SOL_SOCKET
	r.Details["option"] = syscall.SO_BROADCAST
	r.Details["value"] = 1
	fd, err := syscall.Socket(syscall.AF_INET, syscall.SOCK_DGRAM | syscall.SOCK_NONBLOCK | syscall.SOCK_CLOEXEC, 0)
	if err != nil {
		return failure(r, "socket", err)
	}
	defer syscall.Close(fd)
	if err := syscall.SetsockoptInt(fd, syscall.SOL_SOCKET, syscall.SO_BROADCAST, 1); err != nil {
		return failure(r, "setsockopt(SOL_SOCKET,SO_BROADCAST,1)", err)
	}
	return r
}

var goPayload = []byte("go-hmos-app-network\x00go-roundtrip\xff")

func writeAll(conn net.Conn, data []byte) error {
	for len(data) > 0 {
		n, err := conn.Write(data)
		if err != nil {
			return err
		}
		if n == 0 {
			return io.ErrShortWrite
		}
		data = data[n:]
	}
	return nil
}

func goTCP() checkResult {
	r := newResult("go.tcp_roundtrip", "go-net", "net.ListenTCP; net.DialTCP via Dialer; AcceptTCP; bidirectional payload exchange")
	deadline := time.Now().Add(operationTimeout)
	listener, err := net.ListenTCP("tcp4", &net.TCPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil { return failure(r, "ListenTCP", err) }
	defer listener.Close()
	if err := listener.SetDeadline(deadline); err != nil { return failure(r, "listener.SetDeadline", err) }
	dialer := net.Dialer{Deadline: deadline}
	client, err := dialer.Dial("tcp4", listener.Addr().String())
	if err != nil { return failure(r, "Dial", err) }
	defer client.Close()
	if err := client.SetDeadline(deadline); err != nil { return failure(r, "client.SetDeadline", err) }
	server, err := listener.AcceptTCP()
	if err != nil { return failure(r, "AcceptTCP", err) }
	defer server.Close()
	if err := server.SetDeadline(deadline); err != nil { return failure(r, "server.SetDeadline", err) }
	if err := writeAll(client, goPayload); err != nil { return failure(r, "Write(client->server)", err) }
	data := make([]byte, len(goPayload))
	if _, err := io.ReadFull(server, data); err != nil { return failure(r, "Read(server)", err) }
	if !bytes.Equal(data, goPayload) { return failure(r, "verify(server payload)", fmt.Errorf("payload mismatch")) }
	if err := writeAll(server, data); err != nil { return failure(r, "Write(server->client)", err) }
	if _, err := io.ReadFull(client, data); err != nil { return failure(r, "Read(client)", err) }
	if !bytes.Equal(data, goPayload) { return failure(r, "verify(client payload)", fmt.Errorf("payload mismatch")) }
	return r
}

func goUDP() checkResult {
	r := newResult("go.udp_roundtrip", "go-net", "net.ListenUDP twice; WriteToUDP/ReadFromUDP bidirectional payload exchange")
	deadline := time.Now().Add(operationTimeout)
	loopback := &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)}
	server, err := net.ListenUDP("udp4", loopback)
	if err != nil { return failure(r, "ListenUDP(server)", err) }
	defer server.Close()
	if err := server.SetDeadline(deadline); err != nil { return failure(r, "server.SetDeadline", err) }
	client, err := net.ListenUDP("udp4", loopback)
	if err != nil { return failure(r, "ListenUDP(client)", err) }
	defer client.Close()
	if err := client.SetDeadline(deadline); err != nil { return failure(r, "client.SetDeadline", err) }
	if n, err := client.WriteToUDP(goPayload, server.LocalAddr().(*net.UDPAddr)); err != nil {
		return failure(r, "WriteToUDP(client->server)", err)
	} else if n != len(goPayload) { return failure(r, "WriteToUDP(client->server)", io.ErrShortWrite) }
	data := make([]byte, len(goPayload)+1)
	n, peer, err := server.ReadFromUDP(data)
	if err != nil { return failure(r, "ReadFromUDP(server)", err) }
	if !bytes.Equal(data[:n], goPayload) { return failure(r, "verify(server payload)", fmt.Errorf("payload mismatch")) }
	if n, err := server.WriteToUDP(data[:n], peer); err != nil {
		return failure(r, "WriteToUDP(server->client)", err)
	} else if n != len(goPayload) { return failure(r, "WriteToUDP(server->client)", io.ErrShortWrite) }
	n, _, err = client.ReadFromUDP(data)
	if err != nil { return failure(r, "ReadFromUDP(client)", err) }
	if !bytes.Equal(data[:n], goPayload) { return failure(r, "verify(client payload)", fmt.Errorf("payload mismatch")) }
	return r
}

func goInterfaces() checkResult {
	r := newResult("go.net_interfaces", "go-net", "net.Interfaces")
	interfaces, err := net.Interfaces()
	if err != nil { return failure(r, "net.Interfaces", err) }
	if len(interfaces) == 0 { return failure(r, "net.Interfaces", fmt.Errorf("returned no interfaces")) }
	for _, item := range interfaces {
		r.Interfaces = append(r.Interfaces, interfaceAddress{Name: item.Name, Flags: uint32(item.Flags), PrefixLength: -1})
	}
	return r
}

func goInterfaceAddrs(name string) checkResult {
	r := newResult("go.interface_addrs:"+name, "go-net", "net.InterfaceByName; net.Interface.Addrs")
	item, err := net.InterfaceByName(name)
	if err != nil { return failure(r, "net.InterfaceByName", err) }
	addresses, err := item.Addrs()
	if err != nil { return failure(r, "net.Interface.Addrs", err) }
	for _, address := range addresses {
		ip, network, err := net.ParseCIDR(address.String())
		if err != nil { return failure(r, "parse interface CIDR", err) }
		ones, bits := network.Mask.Size()
		family := syscall.AF_INET6
		if bits == 32 { family = syscall.AF_INET }
		r.Interfaces = append(r.Interfaces, interfaceAddress{
			Name: name, Address: ip.String(), Family: family, PrefixLength: ones, Flags: uint32(item.Flags),
		})
	}
	return r
}

func addressKeys(items []interfaceAddress) []string {
	seen := make(map[string]bool)
	for _, item := range items {
		if item.Address == "" { continue }
		ip := net.ParseIP(item.Address)
		address := item.Address
		if ip != nil { address = ip.String() }
		seen[fmt.Sprintf("%s=%s/%d", item.Name, address, item.PrefixLength)] = true
	}
	keys := make([]string, 0, len(seen))
	for key := range seen { keys = append(keys, key) }
	sort.Strings(keys)
	return keys
}

func compareInterfaces(native, goList checkResult, addresses []checkResult) checkResult {
	r := newResult("interfaces.addresses_match", "comparison", "compare canonical per-interface IPv4/IPv6 addresses from getifaddrs and net.Interface.Addrs")
	var goAddresses []interfaceAddress
	ready := native.Passed && goList.Passed
	for _, item := range addresses {
		ready = ready && item.Passed
		goAddresses = append(goAddresses, item.Interfaces...)
	}
	nativeKeys, goKeys := addressKeys(native.Interfaces), addressKeys(goAddresses)
	r.Details = map[string]any{"native_addresses": nativeKeys, "go_addresses": goKeys,
		"native_flags_and_go_net_flags_use_different_bit_definitions": true}
	if !ready { return failure(r, "prerequisite", fmt.Errorf("interface enumeration or address query failed")) }
	if len(nativeKeys) == 0 || len(goKeys) == 0 {
		return failure(r, "compare addresses", fmt.Errorf("no IPv4/IPv6 interface addresses"))
	}
	if strings.Join(nativeKeys, "\n") != strings.Join(goKeys, "\n") {
		return failure(r, "compare addresses", fmt.Errorf("native and Go address sets differ; see details (interfaces may change between snapshots)"))
	}
	return r
}

func buildReport() report {
	var out report
	out.SchemaVersion = 1
	out.CoreRevision = coreRevision
	out.Identity.GOOS = runtime.GOOS
	out.Identity.GOARCH = runtime.GOARCH
	out.Identity.Version = runtime.Version()
	out.Identity.processIdentity = currentProcess()
	out.Failed = []string{}
	out.Notes = []string{
		"Exactly one Go c-shared runtime is loaded; native libc checks are called via cgo in this same app process.",
		"Raw native/go-syscall bind and SO_BROADCAST pairs use identical socket flags and options. Round trips are behavior comparisons; go-net may set additional socket options.",
		"Interface snapshots are sequential; native IFF_* flags and Go net.Flags are not numerically comparable.",
		"Each exchange has a 3-second socket deadline and each check a 5-second outer deadline. The external app runner must enforce its own process deadline.",
	}
	add := func(r checkResult) { out.Checks = append(out.Checks, r) }
	identity := newResult("identity", "go-runtime", "runtime.GOOS/GOARCH")
	if runtime.GOOS != "openharmony" || runtime.GOARCH != "amd64" {
		identity = failure(identity, "target identity", fmt.Errorf("expected openharmony/amd64, got %s/%s", runtime.GOOS, runtime.GOARCH))
	} else if int(C.AF_INET) != syscall.AF_INET || int(C.SOCK_STREAM) != syscall.SOCK_STREAM ||
		int(C.SOCK_DGRAM) != syscall.SOCK_DGRAM || int(C.SOCK_NONBLOCK) != syscall.SOCK_NONBLOCK ||
		int(C.SOCK_CLOEXEC) != syscall.SOCK_CLOEXEC || int(C.SOL_SOCKET) != syscall.SOL_SOCKET ||
		int(C.SO_BROADCAST) != syscall.SO_BROADCAST {
		identity = failure(identity, "native/Go socket constants", fmt.Errorf("raw C and Go socket constants differ"))
	}
	add(identity)
	add(bounded("core.GoCheck", "go-runtime", "pinned c-shared GoCheck(41)", func() checkResult {
		r := newResult("core.GoCheck", "go-runtime", "pinned c-shared GoCheck(41)")
		status := int(GoCheck(C.int(41)))
		r.Details = map[string]any{"return_code": status, "expected_return_code": 0,
			"environment_matches": os.Getenv("OHOS_GO_TEST") == "before-dlopen"}
		if status != 0 { return failure(r, "GoCheck", fmt.Errorf("return code %d, want 0", status)) }
		return r
	}))
	const rawBindOperation = "socket(AF_INET,type|SOCK_NONBLOCK|SOCK_CLOEXEC,0); bind(127.0.0.1:0)"
	const broadcastOperation = "socket(AF_INET,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0); setsockopt(SOL_SOCKET,SO_BROADCAST,1)"
	checks := []struct { name, implementation, operation string; run func() checkResult }{
		{"native.raw_tcp_bind", "native-libc", rawBindOperation, func() checkResult { return nativeCheck("native.raw_tcp_bind", rawBindOperation, C.APP_RAW_TCP_BIND) }},
		{"go.raw_tcp_bind", "go-syscall", rawBindOperation, func() checkResult { return goRawBind("go.raw_tcp_bind", syscall.SOCK_STREAM) }},
		{"native.raw_udp_bind", "native-libc", rawBindOperation, func() checkResult { return nativeCheck("native.raw_udp_bind", rawBindOperation, C.APP_RAW_UDP_BIND) }},
		{"go.raw_udp_bind", "go-syscall", rawBindOperation, func() checkResult { return goRawBind("go.raw_udp_bind", syscall.SOCK_DGRAM) }},
		{"native.raw_udp_broadcast", "native-libc", broadcastOperation, func() checkResult { return nativeCheck("native.raw_udp_broadcast", broadcastOperation, C.APP_RAW_UDP_BROADCAST) }},
		{"go.raw_udp_broadcast", "go-syscall", broadcastOperation, goRawBroadcast},
		{"native.tcp_roundtrip", "native-libc", "socket/bind/listen/connect/accept4/send/recv bidirectional loopback exchange", func() checkResult { return nativeCheck("native.tcp_roundtrip", "socket/bind/listen/connect/accept4/send/recv bidirectional loopback exchange", C.APP_TCP_ROUNDTRIP) }},
		{"go.tcp_roundtrip", "go-net", "TCP bidirectional loopback exchange", goTCP},
		{"native.udp_roundtrip", "native-libc", "socket/bind/sendto/recvfrom bidirectional loopback exchange", func() checkResult { return nativeCheck("native.udp_roundtrip", "socket/bind/sendto/recvfrom bidirectional loopback exchange", C.APP_UDP_ROUNDTRIP) }},
		{"go.udp_roundtrip", "go-net", "UDP bidirectional loopback exchange", goUDP},
	}
	for _, check := range checks { add(bounded(check.name, check.implementation, check.operation, check.run)) }
	native := bounded("native.getifaddrs", "native-libc", "getifaddrs", func() checkResult { return nativeCheck("native.getifaddrs", "getifaddrs", C.APP_GETIFADDRS) })
	add(native)
	goList := bounded("go.net_interfaces", "go-net", "net.Interfaces", goInterfaces)
	add(goList)
	var addresses []checkResult
	for _, item := range goList.Interfaces {
		name := item.Name
		result := bounded("go.interface_addrs:"+name, "go-net", "net.InterfaceByName; net.Interface.Addrs", func() checkResult { return goInterfaceAddrs(name) })
		addresses = append(addresses, result)
		add(result)
	}
	add(compareInterfaces(native, goList, addresses))
	add(bounded("go.system_dns", "go-netgo", "system DNS", goSystemDNS))
	add(bounded("go.system_timezone", "go-time", "system timezone", goSystemTimezone))
	add(bounded("go.system_trust", "go-tls", "system trust", goSystemTrust))
	for _, check := range out.Checks {
		if !check.Passed { out.Failed = append(out.Failed, check.Name) }
	}
	out.OverallPass = len(out.Failed) == 0
	return out
}

// GoAppNetworkCheck returns a NUL-terminated JSON document allocated by libc.
// The N-API host owns it and must release it using GoAppNetworkFree, after copying
// the bytes into its result file. Do not unload a Go c-shared library with dlclose.
//
//export GoAppNetworkCheck
func GoAppNetworkCheck() *C.char {
	data, err := json.Marshal(buildReport())
	if err != nil {
		return C.CString(`{"schema_version":1,"overall_pass":false,"failed":["json.Marshal"]}`)
	}
	return C.CString(string(data))
}

//export GoAppNetworkFree
func GoAppNetworkFree(value *C.char) {
	C.free(unsafe.Pointer(value))
}
