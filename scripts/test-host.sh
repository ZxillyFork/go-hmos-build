#!/usr/bin/env bash
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.
set -euo pipefail
source "$(dirname "$0")/common.sh"
export GOCACHE="$cache_root/host-tests" PATH="$root/bin:$PATH"
unset CGO_ENABLED CC CXX
cd "$root/src"
go version
for tool in compile asm link; do
  identity=$(go tool "$tool" -V=full)
  printf '%s\n' "$identity"
  [[ "$identity" == *-hmos-devel* && "$identity" == *buildID=* ]] || {
    echo "missing distinct development build identity: $tool" >&2; exit 1;
  }
done
# Regression: the modified compiler must also survive the stock compiler's
# populated bootstrap cache, rather than relying only on isolated CI caches.
GOCACHE="$cache_root/bootstrap" go test internal/platform
go test internal/platform internal/buildcfg go/build cmd/go/internal/imports \
  cmd/go/internal/modindex cmd/go/internal/cfg cmd/internal/buildid cmd/internal/obj \
  cmd/internal/obj/arm64 cmd/internal/obj/x86 cmd/internal/objabi
go test cmd/api -run '^TestCheck$' -check
go test cmd/go -run '^TestScript/build_openharmony$'
# Exercise the upstream Go 1.27.2 security fixes with the rebuilt fork.
# Windows junction handling also requires the installer CI's native Windows run.
go test -count=1 -timeout=10m crypto/tls net/textproto net/http \
  net/http/httputil net/http/internal/http2 mime/multipart
go test -count=1 -timeout=10m os \
  -run '^TestRootMulti(Mkdir|MkdirAllShallow|MkdirAllDeep|Lstat|Open|OpenFile|Stat|ReadFile|Readlink)$'
CGO_ENABLED=1 go test -race -count=1 -timeout=5m net/http/internal/http2 \
  -run '^TestServer_HeaderTableSizeDuringWrite$'
for arch in arm64 amd64; do
  # The runtime package itself has Go and assembly sources. This step does not
  # compile runtime/cgo, link the SDK C library, or execute a target binary.
  GOOS=openharmony GOARCH="$arch" CGO_ENABLED=1 CC=cc go build runtime
done
printf 'PASS: focused host tests and target Go/assembly compilation; no SDK link or device execution.\n'
