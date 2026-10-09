package main

/*
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
struct system_dns_config { int32_t error, timeout; uint32_t retry, nonpublic; char servers[5][51]; };
static int system_dns(struct system_dns_config *out) {
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0);
    if (fd < 0) return -errno;
    struct timeval timeout = {3, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    struct sockaddr_un address = {.sun_family = AF_UNIX};
    strcpy(address.sun_path, "/dev/unix/socket/dnsproxyd");
    int ret = connect(fd, (struct sockaddr *)&address, sizeof(address));
    uint32_t request[3] = {(uint32_t)getuid(), 1, 0};
    if (!ret && send(fd, request, sizeof(request), 0) != sizeof(request)) ret = -1;
    if (!ret && recv(fd, out, sizeof(*out), MSG_WAITALL) != sizeof(*out)) ret = -1;
    if (ret) ret = -errno;
    close(fd);
    return ret ? ret : out->error;
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
	status := C.system_dns(&native)
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
	r.Details = map[string]any{"native_servers": expected, "go_servers": got, "native_status": int(status), "native_service_error": int(native.error)}
	if status != 0 {
		return failure(r, "native NetSys configuration", fmt.Errorf("status %d, service error %d", status, native.error))
	}
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
