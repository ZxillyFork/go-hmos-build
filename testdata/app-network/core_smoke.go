// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

package main

import "C"

import (
	"fmt"
	"net"
	"os"
	"runtime"
	"sync"
	"time"
)

//export GoCheck
func GoCheck(seed C.int) C.int {
	if runtime.GOOS != "openharmony" || os.Getenv("OHOS_GO_TEST") != "before-dlopen" {
		return 1
	}
	var wg sync.WaitGroup
	for i := range 4 {
		wg.Go(func() {
			b := make([]byte, 32<<10)
			for j := range b {
				b[j] = byte(int(seed) + i + j)
			}
			runtime.Gosched()
			runtime.KeepAlive(b)
		})
	}
	wg.Wait()
	runtime.GC()
	<-time.After(time.Millisecond)
	if !recoverNilFault() {
		return 3
	}
	return 0
}

//export GoNetworkCheck
func GoNetworkCheck() C.int {
	if _, err := net.Interfaces(); err != nil {
		fmt.Fprintln(os.Stderr, "net.Interfaces:", err)
		return 1
	}
	return 0
}

func recoverNilFault() (ok bool) {
	defer func() { ok = recover() != nil }()
	var p *int
	*p = 1
	return false
}

func main() {}
