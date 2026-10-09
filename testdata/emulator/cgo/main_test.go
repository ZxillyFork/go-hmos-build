// Copyright 2026 The Go Authors. All rights reserved.
// Use of this source code is governed by a BSD-style
// license that can be found in the LICENSE file.

package main

import "testing"

// A host pass checks fixture logic only, not target libc or runtime behavior.
func TestCGOChecks(t *testing.T) {
	if err := checkCGO(); err != nil {
		t.Fatal(err)
	}
}
