#!/usr/bin/env bash
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.
set -euo pipefail

: "${GO_SOURCE_ROOT:?Set GO_SOURCE_ROOT to the separate go-hmos source checkout}"
root=$(cd "$GO_SOURCE_ROOT" && pwd)
test -f "$root/src/make.bash" && test -f "$root/VERSION" || {
  echo 'GO_SOURCE_ROOT is not a Go source checkout' >&2; exit 2;
}
build_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cache_root=${GO_HMOS_CACHE_ROOT:-"$build_root/.cache"}
mkdir -p "$cache_root"
cache_root=$(cd "$cache_root" && pwd)
# These are controlled reproducibility checks. Ignore persistent go env values
# and cross-compilation settings left over from an unrelated shell session.
unset GOOS GOARCH GOHOSTOS GOHOSTARCH GOEXPERIMENT GOFLAGS GOCACHEPROG
export GOROOT="$root" GOENV=off GO111MODULE=off GOTOOLCHAIN=local GOWORK=off
export GOMAXPROCS=${GOMAXPROCS:-4}
