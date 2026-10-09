package main

/*
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <time.h>
struct system_dns_config { int32_t error, timeout; uint32_t retry, nonpublic; char servers[5][51]; };
static int system_dns(struct system_dns_config *out) {
    void *lib = dlopen("libnetsys_client.z.so", RTLD_NOW);
    if (!lib) return -1;
    int32_t (*getconfig)(uint16_t, struct system_dns_config *) = dlsym(lib, "NetSysGetResolvConf");
    int ret = getconfig ? getconfig(0, out) : -1;
    dlclose(lib);
    return ret;
}
static long system_offset(void) {
    time_t epoch = 1700000000;
    struct tm local;
    localtime_r(&epoch, &local);
    return local.tm_gmtoff;
}
*/
import "C"

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"net"
	"reflect"
	"slices"
	"sync"
	"time"
)

func goSystemDNS() checkResult {
	r := newResult("go.system_dns", "go-netgo", "NetSys configuration and public DNS lookup")
	var native C.struct_system_dns_config
	if result := C.system_dns(&native); result != 0 {
		return failure(r, "native NetSys configuration", fmt.Errorf("status %d, service error %d", result, native.error))
	}
	var expected, got []string
	for i := range native.servers {
		if addr := C.GoString(&native.servers[i][0]); addr != "" {
			expected = append(expected, net.JoinHostPort(addr, "53"))
		}
	}
	var mu sync.Mutex
	resolver := &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
		mu.Lock()
		got = append(got, address)
		mu.Unlock()
		return nil, errors.New("configuration capture")
	}}
	_, _ = resolver.LookupIP(context.Background(), "ip4", "go-hmos-config.invalid.")
	slices.Sort(got)
	got = slices.Compact(got)
	slices.Sort(expected)
	r.Details = map[string]any{"native_servers": expected, "go_servers": got}
	if len(got) == 0 || !reflect.DeepEqual(got, expected) {
		return failure(r, "DNS configuration", fmt.Errorf("Go %v, NetSys %v", got, expected))
	}
	ctx, cancel := context.WithTimeout(context.Background(), operationTimeout)
	defer cancel()
	addresses, err := (&net.Resolver{PreferGo: true}).LookupHost(ctx, "example.com")
	r.Details["addresses"] = addresses
	if err != nil {
		return failure(r, "pure Go DNS query", err)
	}
	if len(addresses) == 0 {
		return failure(r, "pure Go DNS query", errors.New("empty answer"))
	}
	return r
}

func goSystemTimezone() checkResult {
	r := newResult("go.system_timezone", "go-time", "system timezone compared with libc")
	_, offset := time.Unix(1700000000, 0).In(time.Local).Zone()
	want := int(C.system_offset())
	r.Details = map[string]any{"location": time.Local.String(), "offset": offset, "native_offset": want}
	if offset != want {
		return failure(r, "local timezone", fmt.Errorf("Go %d, libc %d", offset, want))
	}
	return r
}

func goSystemTrust() checkResult {
	r := newResult("go.system_trust", "go-tls", "system roots and public TLS handshake")
	roots, err := x509.SystemCertPool()
	if err != nil {
		return failure(r, "system roots", err)
	}
	r.Details = map[string]any{"roots": len(roots.Subjects())}
	if len(roots.Subjects()) == 0 {
		return failure(r, "system roots", errors.New("empty trust store"))
	}
	ctx, cancel := context.WithTimeout(context.Background(), operationTimeout)
	defer cancel()
	dialer := &tls.Dialer{NetDialer: &net.Dialer{Timeout: operationTimeout}, Config: &tls.Config{RootCAs: roots}}
	c, err := dialer.DialContext(ctx, "tcp", "example.com:443")
	if err != nil {
		return failure(r, "TLS handshake", err)
	}
	c.Close()
	return r
}
