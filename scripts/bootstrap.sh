#!/usr/bin/env bash
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.
set -euo pipefail
# Resolve the installed stock compiler before selecting the source GOROOT.
bootstrap=${GOROOT_BOOTSTRAP:-$(env -u GOROOT GOTOOLCHAIN=local GOENV=off go env GOROOT)}
source "$(dirname "$0")/common.sh"
export GOROOT_BOOTSTRAP="$bootstrap" GOCACHE="$cache_root/bootstrap"
unset GOROOT CGO_ENABLED CC CXX
(cd "$root/src" && ./make.bash)
"$root/bin/go" version
"$root/bin/go" tool compile -V=full
