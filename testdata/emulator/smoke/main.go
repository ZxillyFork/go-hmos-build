// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

// A self-contained smoke test for an amd64 OpenHarmony system emulator.
package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"fmt"
	"io"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
)

const operationTimeout = 10 * time.Second

var checks = []struct {
	name string
	run  func() error
}{
	{"runtime", checkRuntime},
	{"timers", checkTimers},
	{"files", checkFiles},
	{"tcp", checkTCP},
	{"udp", checkUDP},
	{"interfaces", checkInterfaces},
	{"crypto", checkCrypto},
	{"tls", checkTLS},
}

func main() {
	if runtime.GOOS != "openharmony" || runtime.GOARCH != "amd64" {
		fmt.Fprintf(os.Stderr, "FAIL: expected openharmony/amd64, got %s/%s\n", runtime.GOOS, runtime.GOARCH)
		os.Exit(1)
	}
	// The host runner also imposes a deadline, so runtime timer failure cannot
	// turn a hung smoke program into a successful validation.
	watchdog := time.AfterFunc(90*time.Second, func() {
		fmt.Fprintln(os.Stderr, "FAIL: emulator smoke deadline exceeded")
		os.Exit(2)
	})
	defer watchdog.Stop()
	fmt.Printf("identity=%s/%s version=%s\n", runtime.GOOS, runtime.GOARCH, runtime.Version())
	for _, check := range checks {
		if err := check.run(); err != nil {
			fmt.Fprintf(os.Stderr, "FAIL: %s: %v\n", check.name, err)
			os.Exit(1)
		}
		fmt.Printf("PASS: %s\n", check.name)
	}
	fmt.Println("PASS: emulator-smoke")
}

func checkRuntime() error {
	old := runtime.GOMAXPROCS(4)
	defer runtime.GOMAXPROCS(old)
	const workers, rounds, size = 8, 16, 32 << 10
	var wg sync.WaitGroup
	var total atomic.Uint64
	for worker := range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for round := range rounds {
				data := make([]byte, size)
				for i := range data {
					data[i] = byte(worker + round + i)
				}
				runtime.Gosched()
				var sum uint64
				for _, value := range data {
					sum += uint64(value)
				}
				total.Add(sum)
				runtime.KeepAlive(data)
			}
		}()
	}
	for range 4 {
		runtime.GC()
	}
	wg.Wait()
	want := uint64(workers * rounds * (size / 256) * (255 * 256 / 2))
	if got := total.Load(); got != want {
		return fmt.Errorf("allocation checksum = %d, want %d", got, want)
	}
	runtime.LockOSThread()
	runtime.Gosched()
	runtime.UnlockOSThread()
	if !recoverNilFault() {
		return fmt.Errorf("nil pointer fault did not become a recoverable panic")
	}
	if got := growStack(128); got != 128*129/2 {
		return fmt.Errorf("stack growth checksum = %d", got)
	}
	pcs := make([]uintptr, 16)
	if runtime.Callers(0, pcs) == 0 {
		return fmt.Errorf("runtime.Callers returned no frames")
	}
	return nil
}

func recoverNilFault() (ok bool) {
	defer func() { ok = recover() != nil }()
	var p *int
	*p = 1
	return false
}

//go:noinline
func growStack(n int) int {
	var data [1024]byte
	data[n%len(data)] = byte(n)
	if n == 0 {
		return 0
	}
	sum := growStack(n - 1)
	return sum + int(data[n%len(data)])
}

func checkTimers() error {
	start := time.Now()
	timer := time.NewTimer(5 * time.Millisecond)
	defer timer.Stop()
	<-timer.C
	if time.Since(start) < 5*time.Millisecond {
		return fmt.Errorf("timer fired before its deadline")
	}
	timer.Reset(time.Millisecond)
	<-timer.C
	ticker := time.NewTicker(time.Millisecond)
	defer ticker.Stop()
	for range 3 {
		<-ticker.C
	}
	done := make(chan struct{})
	time.AfterFunc(time.Millisecond, func() { close(done) })
	<-done
	return nil
}

func checkFiles() (err error) {
	dir, err := os.MkdirTemp("", "go-hmos-emulator-")
	if err != nil {
		return err
	}
	defer func() {
		if removeErr := os.RemoveAll(dir); err == nil {
			err = removeErr
		}
	}()
	data := bytes.Repeat([]byte("openharmony\x00\xff\n"), 4096)
	name := filepath.Join(dir, "original")
	file, err := os.OpenFile(name, os.O_CREATE|os.O_EXCL|os.O_RDWR, 0600)
	if err != nil {
		return err
	}
	defer file.Close()
	if _, err := file.Write(data); err != nil {
		return err
	}
	if err := file.Sync(); err != nil {
		return err
	}
	if _, err := file.Seek(0, io.SeekStart); err != nil {
		return err
	}
	got, err := io.ReadAll(file)
	if err != nil || !bytes.Equal(got, data) {
		return fmt.Errorf("file readback: equal=%t error=%v", bytes.Equal(got, data), err)
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := os.Rename(name, filepath.Join(dir, "renamed")); err != nil {
		return err
	}
	entries, err := os.ReadDir(dir)
	if err != nil || len(entries) != 1 || entries[0].Name() != "renamed" {
		return fmt.Errorf("directory readback: %v error=%v", entries, err)
	}
	return nil
}

func checkTCP() error {
	listener, err := net.ListenTCP("tcp4", &net.TCPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		return err
	}
	defer listener.Close()
	deadline := time.Now().Add(operationTimeout)
	if err := listener.SetDeadline(deadline); err != nil {
		return err
	}
	data := []byte("openharmony local TCP\x00\xff")
	serverDone := make(chan error, 1)
	go func() {
		conn, err := listener.AcceptTCP()
		if err != nil {
			serverDone <- err
			return
		}
		defer conn.Close()
		serverDone <- echo(conn, data, deadline)
	}()
	conn, err := net.DialTimeout("tcp4", listener.Addr().String(), operationTimeout)
	if err != nil {
		return err
	}
	defer conn.Close()
	if err := exchange(conn, data, deadline); err != nil {
		return err
	}
	return <-serverDone
}

func echo(conn net.Conn, data []byte, deadline time.Time) error {
	if err := conn.SetDeadline(deadline); err != nil {
		return err
	}
	got := make([]byte, len(data))
	if _, err := io.ReadFull(conn, got); err != nil {
		return err
	}
	if !bytes.Equal(got, data) {
		return fmt.Errorf("server received incorrect payload: %q", got)
	}
	n, err := conn.Write(got)
	if err == nil && n != len(got) {
		err = io.ErrShortWrite
	}
	return err
}

func exchange(conn net.Conn, data []byte, deadline time.Time) error {
	if err := conn.SetDeadline(deadline); err != nil {
		return err
	}
	if n, err := conn.Write(data); err != nil {
		return err
	} else if n != len(data) {
		return io.ErrShortWrite
	}
	got := make([]byte, len(data))
	if _, err := io.ReadFull(conn, got); err != nil {
		return err
	}
	if !bytes.Equal(got, data) {
		return fmt.Errorf("client received incorrect payload: %q", got)
	}
	return nil
}

func checkUDP() error {
	server, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.IPv4(127, 0, 0, 1)})
	if err != nil {
		return err
	}
	defer server.Close()
	client, err := net.DialUDP("udp4", nil, server.LocalAddr().(*net.UDPAddr))
	if err != nil {
		return err
	}
	defer client.Close()
	deadline := time.Now().Add(operationTimeout)
	if err := server.SetDeadline(deadline); err != nil {
		return err
	}
	if err := client.SetDeadline(deadline); err != nil {
		return err
	}
	data := []byte("openharmony local UDP\x00\xff")
	if n, err := client.Write(data); err != nil || n != len(data) {
		return fmt.Errorf("UDP send: n=%d error=%v", n, err)
	}
	buffer := make([]byte, 1024)
	n, address, err := server.ReadFromUDP(buffer)
	if err != nil || !bytes.Equal(buffer[:n], data) {
		return fmt.Errorf("UDP server read: n=%d error=%v", n, err)
	}
	if n, err := server.WriteToUDP(buffer[:n], address); err != nil || n != len(data) {
		return fmt.Errorf("UDP reply: n=%d error=%v", n, err)
	}
	n, err = client.Read(buffer)
	if err != nil || !bytes.Equal(buffer[:n], data) {
		return fmt.Errorf("UDP client read: n=%d error=%v", n, err)
	}
	return nil
}

func checkInterfaces() error {
	interfaces, err := net.Interfaces()
	if err != nil {
		return err
	}
	if len(interfaces) == 0 {
		return fmt.Errorf("net.Interfaces returned no interfaces")
	}
	for _, iface := range interfaces {
		if _, err := iface.Addrs(); err != nil {
			return fmt.Errorf("interface %q: %w", iface.Name, err)
		}
	}
	return nil
}

func checkCrypto() error {
	var first, second [32]byte
	if _, err := rand.Read(first[:]); err != nil {
		return err
	}
	if _, err := rand.Read(second[:]); err != nil {
		return err
	}
	if first == second || first == [32]byte{} || second == [32]byte{} {
		return fmt.Errorf("crypto/rand returned repeated or all-zero output")
	}
	want := "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
	if got := fmt.Sprintf("%x", sha256.Sum256([]byte("abc"))); got != want {
		return fmt.Errorf("SHA-256 = %s, want %s", got, want)
	}
	return nil
}

func checkTLS() error {
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return err
	}
	// Use a generated, explicitly trusted certificate and a fixed validation
	// time. This needs neither external DNS nor system root certificates or a
	// correctly configured emulator wall clock.
	now := time.Unix(1700000000, 0)
	template := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "emulator.invalid"},
		DNSNames:     []string{"emulator.invalid"},
		NotBefore:    now.Add(-time.Hour),
		NotAfter:     now.Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		return err
	}
	certificate, err := x509.ParseCertificate(der)
	if err != nil {
		return err
	}
	roots := x509.NewCertPool()
	roots.AddCert(certificate)
	for _, version := range []uint16{tls.VersionTLS12, tls.VersionTLS13} {
		if err := tlsRoundTrip(der, key, roots, now, version); err != nil {
			return fmt.Errorf("TLS %#x: %w", version, err)
		}
	}
	return nil
}

func tlsRoundTrip(der []byte, key *ecdsa.PrivateKey, roots *x509.CertPool, now time.Time, version uint16) error {
	serverPipe, clientPipe := net.Pipe()
	defer serverPipe.Close()
	defer clientPipe.Close()
	server := tls.Server(serverPipe, &tls.Config{
		Certificates: []tls.Certificate{{Certificate: [][]byte{der}, PrivateKey: key}},
		MinVersion:   version,
		MaxVersion:   version,
	})
	client := tls.Client(clientPipe, &tls.Config{
		RootCAs:    roots,
		ServerName: "emulator.invalid",
		Time:       func() time.Time { return now },
		MinVersion: version,
		MaxVersion: version,
	})
	data := []byte("authenticated in-memory TLS\x00\xff")
	deadline := time.Now().Add(operationTimeout)
	serverDone := make(chan error, 1)
	go func() { serverDone <- echo(server, data, deadline) }()
	if err := exchange(client, data, deadline); err != nil {
		return err
	}
	if err := <-serverDone; err != nil {
		return err
	}
	state := client.ConnectionState()
	if !state.HandshakeComplete || state.Version != version || len(state.VerifiedChains) == 0 {
		return fmt.Errorf("TLS handshake or certificate verification incomplete")
	}
	return nil
}
