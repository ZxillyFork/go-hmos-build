#!/usr/bin/env bash
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.
set -euo pipefail

# Build bounded, self-contained tests for the real amd64 system emulator.
# Compilation and ELF inspection do not establish that the tests were run.
: "${OHOS_NDK_HOME:?Set OHOS_NDK_HOME to the official SDK native directory}"
arch=${GOARCH:-amd64}
source "$(dirname "$0")/common.sh"
if [[ $arch != amd64 ]]; then
  echo "emulator tests require GOARCH=amd64; got $arch" >&2
  exit 2
fi
ndk=$(cd "$OHOS_NDK_HOME" && pwd)
for tool in clang clang++ llvm-readelf; do
  test -x "$ndk/llvm/bin/$tool" || { echo "missing $ndk/llvm/bin/$tool" >&2; exit 2; }
done
test -d "$ndk/sysroot/usr/include" || { echo 'SDK sysroot missing' >&2; exit 2; }
fixtures="$build_root/testdata/emulator"
out=${OUT_DIR:-"$build_root/openharmony-out/$arch"}
mkdir -p "$out"
out=$(cd "$out" && pwd)
work=$(mktemp -d)
trap 'status=$?; printf "exit_status=%s\ndevice_execution=not_performed\n" "$status" > "$out/emulator-build-status.txt"; rm -rf "$work"' EXIT
export GOCACHE="$cache_root/sdk-$arch"
export OHOS_NDK_HOME="$ndk" OHOS_TARGET_TRIPLE=x86_64-linux-ohos
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
export CC="$work/cc" CXX="$work/cxx" GOOS=openharmony GOARCH="$arch" CGO_ENABLED=1
"$CC" -O2 -pthread "$fixtures/native-probe.c" -o "$out/emulator-native-probe"
"$CC" --version > "$out/emulator-compiler-version.txt"
"$root/bin/go" env GOOS GOARCH CGO_ENABLED GOROOT > "$out/emulator-target-env.txt"
"$root/bin/go" version > "$out/emulator-go-version.txt"
git -C "$root" rev-parse HEAD > "$out/emulator-source-revision.txt"
printf 'SDK cross-build and ELF checks only; device execution NOT PERFORMED\n' > "$out/emulator-validation-scope.txt"

check_elf() {
  local binary=$1
  "$ndk/llvm/bin/llvm-readelf" -h -l --wide "$out/$binary" > "$out/$binary.elf.txt"
  grep -Eq 'Machine:.*(X86-64|x86-64)' "$out/$binary.elf.txt" || { echo "wrong machine: $binary" >&2; exit 1; }
  grep -Eq 'Type:.*DYN' "$out/$binary.elf.txt" || { echo "expected PIE: $binary" >&2; exit 1; }
  grep -Fq '/lib/ld-musl-x86_64.so.1' "$out/$binary.elf.txt" || { echo "wrong SDK ELF interpreter: $binary" >&2; exit 1; }
  if grep 'GNU_STACK' "$out/$binary.elf.txt" | grep -q 'RWE'; then
    echo "unexpected executable stack: $binary" >&2
    exit 1
  fi
}
check_elf emulator-native-probe
for fixture in smoke cgo; do
  binary=emulator-smoke
  [[ $fixture == cgo ]] && binary=emulator-cgo-smoke
  (cd "$fixtures" && "$root/bin/go" build -trimpath -buildmode=pie -o "$out/$binary" "./$fixture")
  check_elf "$binary"
done

# Rebuild every listed package rather than trusting stale outputs from a
# previous SDK or core checkout. The manifest is copied only after success.
declare -A seen=()
count=0
while IFS=$'\t' read -r package binary selection timeout extra; do
  [[ -z $package || $package == \#* ]] && continue
  if [[ ! $package =~ ^[a-z][a-z0-9/]*$ || $binary != "${package//\//_}.test" ||
        ! $selection =~ ^\^\(Test[A-Za-z0-9_]+(\|Test[A-Za-z0-9_]+)*\)\$$ ||
        ! $timeout =~ ^[1-9][0-9]*$ || -n $extra || -n ${seen[$package]:-} ]]; then
    echo "invalid or duplicate emulator test manifest row: $package" >&2
    exit 2
  fi
  seen[$package]=1
  # Check the actual GOOS/GOARCH-selected test files, not all files in the
  # directory: a renamed or build-tag-excluded test must not silently vanish.
  "$root/bin/go" list -tags=timetzdata -f '{{range .TestGoFiles}}{{println .}}{{end}}{{range .XTestGoFiles}}{{println .}}{{end}}' "$package" > "$work/test-files"
  test_files=()
  while IFS= read -r test_file; do
    [[ -n $test_file ]] && test_files+=("$root/src/$package/$test_file")
  done < "$work/test-files"
  ((${#test_files[@]} > 0)) || { echo "no target test files: $package" >&2; exit 1; }
  names=${selection#\^\(}
  names=${names%\)\$}
  IFS='|' read -r -a selected_tests <<< "$names"
  for selected_test in "${selected_tests[@]}"; do
    grep -Eq "^func $selected_test[[:space:]]*\\(" "${test_files[@]}" || {
      echo "selected target test is missing: $package.$selected_test" >&2
      exit 1
    }
  done
  # The upstream time tests initialize US/Pacific before selecting tests.
  # Embed tzdata so their init does not need GOROOT/lib/time/zoneinfo.zip.
  "$root/bin/go" test -c -trimpath -tags=timetzdata -buildmode=pie -o "$out/$binary" "$package"
  check_elf "$binary"
  count=$((count + 1))
done < "$fixtures/stdlib-tests.tsv"
((count > 0)) || { echo 'empty emulator test manifest' >&2; exit 2; }
cp "$fixtures/stdlib-tests.tsv" "$out/stdlib-tests.tsv"
printf 'PASS: built emulator smoke programs and %s focused standard-library test binaries; DEVICE EXECUTION NOT PERFORMED. Artifacts: %s\n' "$count" "$out"
