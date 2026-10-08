#!/usr/bin/env bash
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.
set -euo pipefail

# Compile and inspect real SDK artifacts. This script NEVER treats a build as
# a device run. OHOS_NDK_HOME is the extracted public SDK's native directory.
: "${OHOS_NDK_HOME:?Set OHOS_NDK_HOME to the official SDK native directory}"
arch=${GOARCH:-arm64}
source "$(dirname "$0")/common.sh"
export GOCACHE="$cache_root/sdk-$arch"
case "$arch" in
  arm64) triple=aarch64-linux-ohos; interpreter=/lib/ld-musl-aarch64.so.1 ;;
  amd64) triple=x86_64-linux-ohos; interpreter=/lib/ld-musl-x86_64.so.1 ;;
  *) echo "unsupported GOARCH=$arch; use arm64 or amd64" >&2; exit 2 ;;
esac
fixtures="$root/src/cmd/cgo/internal/testcshared/testdata/openharmony"
for fixture in library/main.go hello/main.go loader.c; do
  test -f "$fixtures/$fixture" || { echo "missing core fixture: $fixtures/$fixture" >&2; exit 2; }
done
ndk=$(cd "$OHOS_NDK_HOME" && pwd)
for tool in clang clang++ llvm-readelf; do
  test -x "$ndk/llvm/bin/$tool" || { echo "missing $ndk/llvm/bin/$tool" >&2; exit 2; }
done
test -d "$ndk/sysroot/usr/include" || { echo "SDK sysroot missing" >&2; exit 2; }
out=${OUT_DIR:-"$build_root/openharmony-out/$arch"}
mkdir -p "$out"
out=$(cd "$out" && pwd)
work=$(mktemp -d)
trap 'status=$?; printf "exit_status=%s\ndevice_execution=not_performed\n" "$status" > "$out/build-status.txt"; rm -rf "$work"' EXIT
export OHOS_NDK_HOME="$ndk" OHOS_TARGET_TRIPLE="$triple"
cat > "$work/cc" <<'CC'
#!/usr/bin/env bash
set -euo pipefail
exec "$OHOS_NDK_HOME/llvm/bin/clang" --target="$OHOS_TARGET_TRIPLE" --sysroot="$OHOS_NDK_HOME/sysroot" "$@"
CC
cat > "$work/cxx" <<'CXX'
#!/usr/bin/env bash
set -euo pipefail
exec "$OHOS_NDK_HOME/llvm/bin/clang++" --target="$OHOS_TARGET_TRIPLE" --sysroot="$OHOS_NDK_HOME/sysroot" "$@"
CXX
chmod +x "$work/cc" "$work/cxx"
unset CGO_CFLAGS CGO_CPPFLAGS CGO_CXXFLAGS CGO_FFLAGS CGO_LDFLAGS
export CC="$work/cc" CXX="$work/cxx" GOOS=openharmony GOARCH="$arch" CGO_ENABLED=1 GO111MODULE=off GOTOOLCHAIN=local
# Fail closed on a host clang, wrong sysroot, or unsupported target. Merely
# producing a Linux ELF is not an OpenHarmony cross-build test.
printf '#ifndef __OHOS__\n#error expected OpenHarmony SDK compiler\n#endif\n#include <pthread.h>\n#include <ifaddrs.h>\nint main(void){ return 0; }\n' | "$CC" -x c - -o "$work/sdk-probe"
"$CC" --version > "$out/compiler-version.txt"
"$root/bin/go" version > "$out/go-version.txt"
"$root/bin/go" env GOOS GOARCH CGO_ENABLED GOROOT > "$out/target-env.txt"
git -C "$root" rev-parse HEAD > "$out/source-revision.txt"
printf 'compile/link/ELF inspection only; device execution NOT PERFORMED\n' > "$out/validation-scope.txt"
# In GOPATH mode, Go accepts relative package directories, not absolute ones.
# Keep these fixtures in the source checkout instead of copying them here.
build_fixture() {
  local package=$1
  shift
  (cd "$fixtures" && "$root/bin/go" build "$@" "./$package")
}
build_fixture library -trimpath -buildmode=c-shared -o "$out/libgo_hmos_test.so"
build_fixture library -trimpath -buildmode=c-archive -o "$out/libgo_hmos_test.a"
build_fixture hello -trimpath -buildmode=pie -o "$out/hello"
"$CC" -O2 -pthread "$fixtures/loader.c" -ldl -o "$out/loader"
readelf="$ndk/llvm/bin/llvm-readelf"
"$readelf" -h -l -d -r --wide "$out/libgo_hmos_test.so" > "$out/library-elf.txt"
grep -q 'TLSDESC' "$out/library-elf.txt" || { echo "missing dynamic TLS descriptor" >&2; exit 1; }
if grep -Eq 'STATIC_TLS|TEXTREL|R_AARCH64_TLS_TPREL|R_X86_64_TPOFF' "$out/library-elf.txt"; then
  echo "unexpected initial-exec TLS in dlopen library" >&2; exit 1
fi
grep -Eq '^[[:space:]]*TLS[[:space:]]' "$out/library-elf.txt" || { echo "missing PT_TLS" >&2; exit 1; }
if grep -E 'GNU_STACK' "$out/library-elf.txt" | grep -q 'RWE'; then
  echo "unexpected executable stack" >&2; exit 1
fi
case "$arch" in
  arm64) grep -Eq 'Machine:.*AArch64' "$out/library-elf.txt" ;;
  amd64) grep -Eq 'Machine:.*(X86-64|x86-64)' "$out/library-elf.txt" ;;
esac
"$readelf" -h -l --wide "$out/hello" > "$out/executable-elf.txt"
grep -Fq "$interpreter" "$out/executable-elf.txt" || { echo "wrong SDK ELF interpreter" >&2; exit 1; }
grep -Eq 'Type:.*DYN' "$out/executable-elf.txt" || { echo "expected PIE" >&2; exit 1; }
# Exercise netgo file selection even though platform interface discovery still
# correctly needs libc. DNS via netgo is opt-in and may lack system netid policy.
build_fixture library -tags=netgo -buildmode=c-shared -o "$out/libgo_hmos_netgo.so"
for package in runtime os/signal runtime/pprof net time crypto/x509; do
  "${root}/bin/go" test -c -o "$out/${package//\//_}.test" "$package"
done
if [[ ${BUILD_NATIVE_TOOLS:-0} == 1 ]]; then
  mkdir -p "$out/bin" "$out/pkg/tool/openharmony_$arch"
  for tool in asm cgo compile cover fix link preprofile vet; do
    "$root/bin/go" build -o "$out/pkg/tool/openharmony_$arch/$tool" "cmd/$tool"
  done
  "$root/bin/go" build -o "$out/bin/go" cmd/go
  "$root/bin/go" build -o "$out/bin/gofmt" cmd/gofmt
  "$root/bin/go" build -o "$out/pkg/tool/openharmony_$arch/dist" cmd/dist
fi
printf 'PASS: SDK compile/link/ELF checks for %s; DEVICE EXECUTION NOT PERFORMED. Artifacts: %s\n' "$triple" "$out"
