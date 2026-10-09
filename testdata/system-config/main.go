package main

import (
	"context"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"os/user"
	"runtime"
	"slices"
	"strings"
	"sync"
	"time"
)

func main() {
	out := map[string]any{"goos": runtime.GOOS, "goarch": runtime.GOARCH, "uid": os.Getuid()}
	var servers []string
	var mu sync.Mutex
	resolver := &net.Resolver{PreferGo: true, Dial: func(ctx context.Context, network, address string) (net.Conn, error) {
		mu.Lock()
		servers = append(servers, address)
		mu.Unlock()
		return nil, errors.New("configuration probe")
	}}
	_, _ = resolver.LookupIP(context.Background(), "ip4", "go-hmos-config.invalid.")
	slices.Sort(servers)
	out["dns_servers"] = slices.Compact(servers)
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()
	addresses, err := net.DefaultResolver.LookupHost(ctx, "example.com")
	out["lookup_addresses"] = addresses
	if err != nil {
		out["lookup_error"] = err.Error()
	}
	instant := time.Unix(1700000000, 0).In(time.Local)
	zone, offset := instant.Zone()
	out["timezone"] = time.Local.String()
	out["zone"] = zone
	out["offset"] = offset
	ifaces, err := net.Interfaces()
	if err != nil {
		out["interfaces_error"] = err.Error()
	}
	var names, interfaceAddresses []string
	for _, iface := range ifaces {
		names = append(names, iface.Name)
		addresses, err := iface.Addrs()
		if err != nil {
			out["addresses_error"] = err.Error()
		}
		for _, addr := range addresses {
			interfaceAddresses = append(interfaceAddresses, iface.Name+"="+addr.String())
		}
	}
	slices.Sort(names)
	slices.Sort(interfaceAddresses)
	out["interfaces"] = names
	out["interface_addresses"] = interfaceAddresses
	roots, err := x509.SystemCertPool()
	if err != nil {
		out["roots_error"] = err.Error()
	} else {
		out["roots"] = len(roots.Subjects())
	}
	current, err := user.Current()
	if err != nil {
		out["user_error"] = err.Error()
	} else {
		out["username"] = current.Username
		out["home"] = current.HomeDir
	}
	hostname, err := os.Hostname()
	if err != nil {
		out["hostname_error"] = err.Error()
	} else {
		out["hostname"] = hostname
	}
	out["tmpdir"] = os.TempDir()
	data, err := json.Marshal(out)
	if err != nil {
		panic(err)
	}
	fmt.Println(strings.TrimSpace(string(data)))
}
