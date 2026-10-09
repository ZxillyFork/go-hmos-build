// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

// Exercise cgo calls, C thread-local storage, and callbacks from C pthreads.
package main

/*
#cgo CFLAGS: -pthread
#cgo LDFLAGS: -pthread
#include "native.h"
*/
import "C"

import (
	"fmt"
	"os"
	"runtime"
	"sync"
	"sync/atomic"
	"time"
)

var callbacks atomic.Int64

//export emulatorGoCallback
func emulatorGoCallback(seed C.int) C.int {
	data := make([]byte, 4096)
	for i := range data {
		data[i] = byte(int(seed) + i)
	}
	runtime.Gosched()
	runtime.KeepAlive(data)
	callbacks.Add(1)
	return seed*2 + 1
}

func main() {
	if runtime.GOOS != "openharmony" || runtime.GOARCH != "amd64" {
		fmt.Fprintf(os.Stderr, "FAIL: expected openharmony/amd64, got %s/%s\n", runtime.GOOS, runtime.GOARCH)
		os.Exit(1)
	}
	watchdog := time.AfterFunc(60*time.Second, func() {
		fmt.Fprintln(os.Stderr, "FAIL: cgo smoke deadline exceeded")
		os.Exit(2)
	})
	defer watchdog.Stop()
	if err := checkCGO(); err != nil {
		fmt.Fprintln(os.Stderr, "FAIL:", err)
		os.Exit(1)
	}
	fmt.Println("PASS: emulator-cgo-smoke")
}

func checkCGO() error {
	const workers, rounds = 8, 128
	var wg sync.WaitGroup
	errors := make(chan error, workers)
	ready := make(chan struct{}, workers)
	start := make(chan struct{})
	for worker := range workers {
		wg.Add(1)
		go func() {
			defer wg.Done()
			runtime.LockOSThread()
			defer runtime.UnlockOSThread()
			seed := C.int(worker + 1)
			C.emulatorSetTLS(seed)
			ready <- struct{}{}
			<-start
			for round := range rounds {
				runtime.Gosched()
				if got := C.emulatorGetTLS(); got != seed {
					errors <- fmt.Errorf("C TLS value = %d, want %d", got, seed)
					return
				}
				if got := C.emulatorAdd(seed, C.int(round)); got != seed+C.int(round) {
					errors <- fmt.Errorf("C arithmetic result = %d", got)
					return
				}
			}
		}()
	}
	for range workers {
		<-ready
	}
	close(start)
	wg.Wait()
	close(errors)
	for err := range errors {
		return err
	}
	before := callbacks.Load()
	if status := C.emulatorPthreads(); status != 0 {
		return fmt.Errorf("C pthread callback/TLS check failed: %d", status)
	}
	if count := callbacks.Load() - before; count != 4*32 {
		return fmt.Errorf("C thread callbacks = %d, want 128", count)
	}
	runtime.GC()
	return nil
}
