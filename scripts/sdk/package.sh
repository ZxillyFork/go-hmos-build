#!/usr/bin/env bash
# Package the exact already-built Go source revision. No native SDK is included.
set -euo pipefail
source "$(dirname "$0")/../common.sh"
: "${SDK_OUTPUT_DIR:?Set SDK_OUTPUT_DIR to an empty output directory}"
python3 "$build_root/scripts/sdk/metadata.py" check
expected=$(python3 "$build_root/scripts/source-pin.py")
test "$(git -C "$root" rev-parse HEAD)" = "$expected"
test -z "$(git -C "$root" status --porcelain --untracked-files=no)"
test "$("$root/bin/go" env GOHOSTOS GOHOSTARCH | paste -sd /)" = linux/amd64
version=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["go_version"])' "$build_root/sdk-release.json")
test "$(head -n 1 "$root/VERSION")" = "$version"
test "$("$root/bin/go" env GOVERSION)" = "$version"
mkdir -p "$SDK_OUTPUT_DIR"
out=$(cd "$SDK_OUTPUT_DIR" && pwd)
test -z "$(ls -A "$out")" || { echo 'Output directory must be empty' >&2; exit 2; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/go"
git -C "$root" archive HEAD | tar -x -C "$work/go"
# dist bootstrap writes these ignored Go sources. They are required by an
# extracted SDK (notably time/tzdata and rebuilding cmd/compile), so a plain
# git archive is insufficient. Keep this allowlist aligned with cmd/dist.
for generated in \
  src/cmd/cgo/zdefaultcc.go \
  src/cmd/go/internal/cfg/zdefaultcc.go \
  src/cmd/internal/objabi/zbootstrap.go \
  src/internal/buildcfg/zbootstrap.go \
  src/internal/runtime/sys/zversion.go \
  src/time/tzdata/zzipdata.go; do
  test -f "$root/$generated"
  cp -a "$root/$generated" "$work/go/$generated"
done
# Copy only Go build products. In particular never copy .sdk, credentials,
# Git metadata, intermediate bootstrap trees, caches or cross-SDK tools.
mkdir -p "$work/go/bin" "$work/go/pkg/tool"
cp -a "$root/bin/go" "$root/bin/gofmt" "$work/go/bin/"
cp -a "$root/pkg/tool/linux_amd64" "$work/go/pkg/tool/"
cp -a "$root/pkg/include" "$work/go/pkg/"
python3 "$build_root/scripts/sdk/metadata.py" provenance > "$work/go/HMOS-SDK.json"
printf '%s\n' "$expected" > "$work/go/core-revision.txt"
cp "$work/go/HMOS-SDK.json" "$out/provenance.json"
archive="$version.linux-amd64.tar.gz"
epoch=$(git -C "$root" show -s --format=%ct HEAD)
# Normalize archive metadata; source build reproducibility is not asserted.
tar --sort=name --mtime="@$epoch" --owner=0 --group=0 --numeric-owner \
  -cf - -C "$work" go | gzip -n -9 > "$out/$archive"
(cd "$out" && sha256sum "$archive" provenance.json > SHA256SUMS)
python3 "$build_root/scripts/sdk/metadata.py" manifest "$out" > "$out/sdk-manifest.json"
python3 "$build_root/scripts/sdk/metadata.py" notes "$out" > "$out/RELEASE-NOTES.md"
printf 'Packaged %s from core %s\n' "$archive" "$expected"
