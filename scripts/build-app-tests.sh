#!/usr/bin/env bash
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license in LICENSE.
set -euo pipefail
: "${OHOS_NDK_HOME:?Set OHOS_NDK_HOME to the official public SDK native directory}"
: "${EMULATOR_ROOT:?Set EMULATOR_ROOT to the verified CLI extraction root}"
source "$(dirname "$0")/common.sh"
ndk=$(cd "$OHOS_NDK_HOME" && pwd)
cli=$(cd "$EMULATOR_ROOT/command-line-tools" && pwd)
project="$build_root/.app-build"
out="$build_root/.app-out"
test ! -e "$project" || { echo 'Refusing a stale app build directory' >&2; exit 2; }
mkdir -p "$out"
cp -R "$build_root/testdata/app-host" "$project"
mkdir -p "$project/entry/libs/x86_64"
export OHOS_NDK_HOME="$ndk"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/cc" <<'CC'
#!/usr/bin/env bash
set -euo pipefail
exec "$OHOS_NDK_HOME/llvm/bin/clang" --target=x86_64-linux-ohos --sysroot="$OHOS_NDK_HOME/sysroot" "$@"
CC
chmod +x "$work/cc"
export CC="$work/cc" GOOS=openharmony GOARCH=amd64 CGO_ENABLED=1 GOCACHE="$cache_root/sdk-amd64"
unset CGO_CFLAGS CGO_CPPFLAGS CGO_CXXFLAGS CGO_FFLAGS CGO_LDFLAGS
# The original core fixture is copied byte-for-byte, not modified or rebuilt
# with a different core. One shared Go runtime also contains the new checks.
cmp "$root/src/cmd/cgo/internal/testcshared/testdata/openharmony/library/main.go" \
    "$build_root/testdata/app-network/core_smoke.go"
(cd "$build_root/testdata/app-network" && "$root/bin/go" build -tags=netgo,osusergo -trimpath -buildmode=c-shared \
  -o "$project/entry/libs/x86_64/libgo_app_network.so" .)
mv "$project/entry/libs/x86_64/libgo_app_network.h" "$out/"
"$CC" -O2 -fPIC -shared "$project/entry/src/main/cpp/napi_host.c" \
  -o "$project/entry/libs/x86_64/libgohmos.so" -lace_napi.z -ldl
for lib in "$project"/entry/libs/x86_64/*.so; do
  "$ndk/llvm/bin/llvm-readelf" -h -l -d --wide "$lib" > "$out/$(basename "$lib").elf.txt"
  grep -Eq 'Machine:.*(X86-64|x86-64)' "$out/$(basename "$lib").elf.txt"
  if grep -Eq 'TEXTREL' "$out/$(basename "$lib").elf.txt"; then exit 1; fi
done
"$root/bin/go" env GOOS GOARCH CGO_ENABLED GOROOT > "$out/go-target-env.txt"
git -C "$root" rev-parse HEAD > "$out/core-revision.txt"
git -C "$build_root" rev-parse HEAD > "$out/build-revision.txt"
# Use the normal bundled build tools, with no signing credentials/configuration.
export DEVECO_NODE_HOME="$cli/tool/node" DEVECO_SDK_HOME="$cli/sdk" OHPM_HOME="$cli/ohpm" HOS_SDK_HOME="$cli/sdk"
export PATH="$cli/bin:$DEVECO_NODE_HOME/bin:$PATH"
printf 'hwsdk.dir=%s/sdk\nsdk.dir=%s/sdk\n' "$cli" "$cli" > "$project/local.properties"
cd "$project"
node --version
java -version
hvigorw --version
ohpm --version
ohpm install
hvigorw assembleHap --mode module -p module=entry@default -p product=default -p buildMode=debug --no-daemon
mapfile -t haps < <(find entry/build -type f -name '*-unsigned.hap')
((${#haps[@]} == 1)) || { echo "Expected exactly one unsigned debug HAP; got ${#haps[@]}" >&2; exit 1; }
cp "${haps[0]}" "$out/entry-default-unsigned.hap"
python3 "$build_root/scripts/app/validate_hap.py" "$out/entry-default-unsigned.hap" "$out"
# Record tool hashes only; do not redistribute SDK/CLI sources or keys.
for file in src/tasks/sign-hap.js src/tasks/sign/sign-util.js src/utils/keystore-utils.js; do
  if test -f "$cli/hvigor/hvigor-ohos-plugin/$file"; then
    sha256sum "$cli/hvigor/hvigor-ohos-plugin/$file" >> "$out/signing-tool-hashes.txt"
  fi
done
cp "$cli/sdk/default/sdk-pkg.json" "$out/cli-sdk-pkg.json"
printf 'Built normal unsigned debug HAP; app execution has NOT happened.\n'
