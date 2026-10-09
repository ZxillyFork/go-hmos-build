#!/usr/bin/env bash
# Run only after official actions/setup-go has selected the SDK.
set -euo pipefail
build_root=$(cd "$(dirname "$0")/../.." && pwd)
export GOENV=off GOTOOLCHAIN=local GOWORK=off
unset GOOS GOARCH GOFLAGS GOEXPERIMENT GOCACHEPROG
export GOMAXPROCS=${GOMAXPROCS:-4}
expected=$(python3 "$build_root/scripts/source-pin.py")
root=$(go env GOROOT)
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["go_version"])' "$build_root/sdk-release.json")
test "$(go env GOVERSION)" = "$version"
test "$(go env GOHOSTOS GOHOSTARCH | paste -sd /)" = linux/amd64
python3 - "$root/HMOS-SDK.json" "$expected" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
assert p['source_commit'] == sys.argv[2], p
assert p['native_sdk_included'] is False, p
PY
for tool in compile asm link; do
  identity=$(go tool "$tool" -V=full)
  [[ "$identity" == *-hmos-devel* && "$identity" == *buildID=* ]]
done
# Never let a populated source/host cache hide a missing SDK source file.
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
export GOCACHE="$work/cache"
go build time/tzdata internal/buildcfg cmd/internal/objabi cmd/cgo cmd/compile cmd/go
for arch in arm64 amd64; do
  go tool dist list | grep -Fx "openharmony/$arch"
  GOOS=openharmony GOARCH="$arch" CGO_ENABLED=1 CC=cc go build runtime
done
# This fixture records the actual target identity in its binary metadata.
cat > "$work/main.go" <<'GO'
package main
import ("fmt"; "runtime")
func main() { fmt.Println(runtime.GOOS, runtime.GOARCH) }
GO
go build -trimpath -tags=timetzdata -o "$work/hello" "$work/main.go"
test "$("$work/hello")" = 'linux amd64'
for arch in arm64 amd64; do
  GOOS=openharmony GOARCH="$arch" CGO_ENABLED=0 CC=/nonexistent go build net time crypto/x509 os/user
  GOOS=openharmony GOARCH="$arch" CGO_ENABLED=0 CC=/nonexistent go build -trimpath -o "$work/standalone-$arch" "$work/main.go"
  readelf -h -l -d "$work/standalone-$arch" > "$work/standalone-$arch.elf.txt"
  grep -Eq 'Type:.*EXEC' "$work/standalone-$arch.elf.txt"
  if grep -Eq 'INTERP|DYNAMIC|NEEDED' "$work/standalone-$arch.elf.txt"; then
    echo "unexpected standalone dynamic dependency: $arch" >&2; exit 1
  fi
  go version -m "$work/standalone-$arch" | grep -F 'CGO_ENABLED=0'
done
if [[ -n ${OHOS_NDK_HOME:-} ]]; then
  ndk=$(cd "$OHOS_NDK_HOME" && pwd)
  export OHOS_NDK_HOME="$ndk"
  cat > "$work/cc" <<'CC'
#!/usr/bin/env bash
set -euo pipefail
exec "$OHOS_NDK_HOME/llvm/bin/clang" --target="$OHOS_TARGET_TRIPLE" --sysroot="$OHOS_NDK_HOME/sysroot" "$@"
CC
  chmod +x "$work/cc"
  for arch in arm64 amd64; do
    case "$arch" in
      arm64) export OHOS_TARGET_TRIPLE=aarch64-linux-ohos; machine=AArch64; loader=ld-musl-aarch64.so.1 ;;
      amd64) export OHOS_TARGET_TRIPLE=x86_64-linux-ohos; machine=X86-64; loader=ld-musl-x86_64.so.1 ;;
    esac
    printf '#ifndef __OHOS__\n#error expected OpenHarmony compiler\n#endif\nint main(void){return 0;}\n' | "$work/cc" -x c - -o "$work/probe"
    export GOOS=openharmony GOARCH="$arch" CGO_ENABLED=1 CC="$work/cc"
    go build -trimpath -buildmode=pie -o "$work/hello-$arch" "$work/main.go"
    "$ndk/llvm/bin/llvm-readelf" -h -l "$work/hello-$arch" > "$work/elf-$arch.txt"
    grep -Fq "$loader" "$work/elf-$arch.txt"
    grep -Fq "$machine" "$work/elf-$arch.txt"
    go version -m "$work/hello-$arch" | grep -F 'GOOS=openharmony'
    GO111MODULE=off go build -trimpath -buildmode=c-shared -o "$work/lib-$arch.so" \
      "$root/src/cmd/cgo/internal/testcshared/testdata/openharmony/library/main.go"
    "$ndk/llvm/bin/llvm-readelf" -h -l -d -r "$work/lib-$arch.so" > "$work/library-$arch.txt"
    grep -q TLSDESC "$work/library-$arch.txt"
    if grep -Eq 'STATIC_TLS|TEXTREL|R_AARCH64_TLS_TPREL|R_X86_64_TPOFF' "$work/library-$arch.txt"; then
      echo 'invalid dynamic library TLS/relocations' >&2; exit 1
    fi
    unset GOOS GOARCH
  done
fi
printf 'Verified setup-go-selected HMOS package from %s (target execution not performed).\n' "$expected"
