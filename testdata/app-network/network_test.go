// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

package main

import (
	"encoding/json"
	"fmt"
	"reflect"
	"runtime"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestRawPairsUseIdenticalOperations(t *testing.T) {
	tests := []struct {
		name string
		native, goCheck func() checkResult
	}{
		{"tcp_bind", func() checkResult { return nativeCheck("native.raw_tcp_bind", "bind", 0) }, func() checkResult { return goRawBind("go.raw_tcp_bind", syscall.SOCK_STREAM) }},
		{"udp_bind", func() checkResult { return nativeCheck("native.raw_udp_bind", "bind", 1) }, func() checkResult { return goRawBind("go.raw_udp_bind", syscall.SOCK_DGRAM) }},
		{"udp_broadcast", func() checkResult { return nativeCheck("native.raw_udp_broadcast", "setsockopt", 2) }, goRawBroadcast},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			native, goResult := test.native(), test.goCheck()
			if native.Process != goResult.Process || native.Process != currentProcess() {
				t.Fatalf("not the same process: native=%+v go=%+v", native.Process, goResult.Process)
			}
			if !reflect.DeepEqual(native.Details, goResult.Details) {
				t.Fatalf("raw operations differ: native=%+v go=%+v", native.Details, goResult.Details)
			}
			for _, result := range []checkResult{native, goResult} {
				if !result.Passed { t.Errorf("%s: stage=%s errno=%d error=%s", result.Name, result.Stage, result.Errno, result.Error) }
			}
		})
	}
}

func TestLoopbackRoundTrips(t *testing.T) {
	tests := []struct { name string; run func() checkResult }{
		{"native_tcp", func() checkResult { return nativeCheck("native.tcp_roundtrip", "TCP round trip", 3) }},
		{"go_tcp", goTCP},
		{"native_udp", func() checkResult { return nativeCheck("native.udp_roundtrip", "UDP round trip", 4) }},
		{"go_udp", goUDP},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			r := bounded(test.name, "test", "round trip", test.run)
			if !r.Passed { t.Fatalf("stage=%s errno=%d error=%s", r.Stage, r.Errno, r.Error) }
		})
	}
}

func TestReportContractAndHostIdentity(t *testing.T) {
	t.Setenv("OHOS_GO_TEST", "before-dlopen")
	r := buildReport()
	data, err := json.Marshal(r)
	if err != nil { t.Fatal(err) }
	var wire map[string]any
	if err := json.Unmarshal(data, &wire); err != nil { t.Fatal(err) }
	identity := wire["identity"].(map[string]any)
	if identity["goos"] != runtime.GOOS || identity["goarch"] != runtime.GOARCH || identity["pid"] == nil || identity["uid"] == nil {
		t.Fatalf("missing/misreported identity: %s", data)
	}
	seen := make(map[string]checkResult)
	var failures []string
	for _, result := range r.Checks {
		if _, duplicate := seen[result.Name]; duplicate { t.Fatalf("duplicate result: %s", result.Name) }
		seen[result.Name] = result
		if result.Process != currentProcess() { t.Fatalf("wrong process: %+v", result) }
		if !result.Passed { failures = append(failures, result.Name) }
	}
	required := []string{"identity", "core.GoCheck", "native.raw_tcp_bind", "go.raw_tcp_bind",
		"native.raw_udp_bind", "go.raw_udp_bind", "native.raw_udp_broadcast", "go.raw_udp_broadcast",
		"native.tcp_roundtrip", "go.tcp_roundtrip", "native.udp_roundtrip", "go.udp_roundtrip",
		"native.getifaddrs", "go.net_interfaces", "interfaces.addresses_match"}
	for _, name := range required {
		if _, ok := seen[name]; !ok { t.Errorf("missing independent check: %s", name) }
	}
	if strings.Join(failures, ",") != strings.Join(r.Failed, ",") || r.OverallPass != (len(failures) == 0) {
		t.Fatalf("inconsistent overall result: %s", data)
	}
	if runtime.GOOS != "openharmony" || runtime.GOARCH != "amd64" {
		if r.OverallPass || seen["identity"].Passed { t.Fatal("host execution claimed target validation") }
	}
	if runtime.GOOS != "openharmony" && seen["core.GoCheck"].Passed {
		t.Fatal("pinned core fixture unexpectedly passed on a host OS")
	}
	if _, ok := wire["checks"].([]any); !ok { t.Fatalf("missing checks array: %s", data) }
}

func TestInterfaceAddressComparison(t *testing.T) {
	native := newResult("native.getifaddrs", "native-libc", "getifaddrs")
	native.Interfaces = []interfaceAddress{
		{Name: "lo", Address: "127.0.0.1", PrefixLength: 8},
		{Name: "lo", Address: "0:0:0:0:0:0:0:1", PrefixLength: 128},
		{Name: "lo", Address: "127.0.0.1", PrefixLength: 8},
	}
	list := newResult("go.net_interfaces", "go-net", "net.Interfaces")
	addresses := newResult("go.interface_addrs:lo", "go-net", "Addrs")
	addresses.Interfaces = []interfaceAddress{
		{Name: "lo", Address: "::1", PrefixLength: 128},
		{Name: "lo", Address: "127.0.0.1", PrefixLength: 8},
	}
	if result := compareInterfaces(native, list, []checkResult{addresses}); !result.Passed { t.Fatalf("equivalent snapshots differ: %+v", result) }
	addresses.Interfaces[1].PrefixLength = 32
	if compareInterfaces(native, list, []checkResult{addresses}).Passed { t.Fatal("different prefix silently passed") }
	addresses.Passed = false
	if result := compareInterfaces(native, list, []checkResult{addresses}); result.Passed || result.Stage != "prerequisite" {
		t.Fatalf("failed address lookup silently passed: %+v", result)
	}
}

func TestWrappedErrnoAndPanicContinue(t *testing.T) {
	r := failure(newResult("error", "test", "test"), "bind", fmt.Errorf("wrapped: %w", syscall.EPERM))
	if r.Passed || r.Errno != int(syscall.EPERM) || r.Stage != "bind" { t.Fatalf("lost errno: %+v", r) }
	r = bounded("panic", "test", "test", func() checkResult { panic("injected") })
	if r.Passed || r.Stage != "panic" || !strings.Contains(r.Error, "injected") { t.Fatalf("panic swallowed: %+v", r) }
	r = bounded("after-panic", "test", "test", func() checkResult { return newResult("after-panic", "test", "test") })
	if !r.Passed { t.Fatalf("independent check did not continue: %+v", r) }
}

func TestOuterDeadline(t *testing.T) {
	release := make(chan struct{})
	defer close(release)
	start := time.Now()
	r := bounded("blocked", "test", "injected blocking worker", func() checkResult {
		<-release
		return newResult("blocked", "test", "test")
	})
	if r.Passed || !r.TimedOut || r.Stage != "check deadline" { t.Fatalf("deadline was not a failure: %+v", r) }
	if elapsed := time.Since(start); elapsed > checkTimeout + 3 * time.Second { t.Fatalf("deadline took %v", elapsed) }
}
