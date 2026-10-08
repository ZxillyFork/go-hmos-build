#!/usr/bin/env bash
# Copyright 2026 The Go Authors. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.
set -euo pipefail
# Explicit opt-in helper for the official public OpenHarmony SDK. It does not
# obtain Huawei's commercial HarmonyOS NEXT SDK or accept click-through terms.
: "${SDK_DOWNLOAD_DIR:?Set SDK_DOWNLOAD_DIR to an empty scratch directory}"
mkdir -p "$SDK_DOWNLOAD_DIR"
destination=$(cd "$SDK_DOWNLOAD_DIR" && pwd)
if [[ -e "$destination/extracted" || -e "$destination/native-path.txt" ]]; then
  echo 'SDK_DOWNLOAD_DIR already contains an extracted SDK; choose an empty directory' >&2
  exit 2
fi
work=$(mktemp -d "$destination/.sdk-download.XXXXXX")
trap 'rm -rf "$work"' EXIT
cd "$work"
base=https://repo.huaweicloud.com/openharmony/os/6.1-Release
archive=ohos-sdk-windows_linux-public.tar.gz
curl --proto '=https' --proto-redir '=https' --fail --location --retry 2 \
  "$base/$archive.sha256" -o "$archive.sha256"
# The official file contains one bare SHA-256, not a caller-supplied URL.
digest=$(tr -d '\r\n' < "$archive.sha256")
[[ "$digest" =~ ^[0-9a-fA-F]{64}$ ]] || {
  echo 'official checksum unavailable or invalid' >&2; exit 1;
}
printf 'Official SDK: %s/%s\nSHA-256: %s\n' "$base" "$archive" "$digest"
curl --proto '=https' --proto-redir '=https' --fail --location --retry 2 \
  "$base/$archive" -o "$archive"
printf '%s  %s\n' "$digest" "$archive" | sha256sum --check -
# List completely before filtering, so pipefail cannot turn an early grep/head
# exit into a spurious SIGPIPE failure for a large tar archive.
tar -tzf "$archive" > archive-members.txt
mapfile -t members < <(grep -E '(^|/)linux/native[^/]*\.zip$' archive-members.txt || true)
if [[ ${#members[@]} != 1 ]]; then
  echo 'expected exactly one Linux native SDK zip in verified archive' >&2
  cat archive-members.txt >&2
  exit 1
fi
member=${members[0]}
case "/$member/" in
  *'/../'*|*'/./../'*|//* ) echo 'unsafe native SDK archive member' >&2; exit 1 ;;
esac
tar -xzf "$archive" -- "$member"
mkdir extracted
unzip -q "$member" -d extracted
# LLVM commonly installs clang as a symlink to clang-N. Follow it when finding
# the real compiler; do not mistake Windows packages or a stale SDK for Linux.
mapfile -t compilers < <(find -L "$work/extracted" -type f -path '*/llvm/bin/clang' -print)
if [[ ${#compilers[@]} != 1 || ! -x "${compilers[0]:-}" ]]; then
  echo 'SDK compiler missing or ambiguous after extraction; actual SDK layout:' >&2
  find "$work/extracted" -maxdepth 7 -name 'clang*' -ls >&2
  exit 1
fi
native=${compilers[0]%/llvm/bin/clang}
for tool in clang++ llvm-readelf; do
  test -x "$native/llvm/bin/$tool" || { echo "SDK missing executable $tool" >&2; exit 1; }
done
test -d "$native/sysroot/usr/include" || { echo 'SDK sysroot headers missing' >&2; exit 1; }
relative=${native#"$work/extracted"}
mv extracted "$destination/extracted"
printf '%s\n' "$destination/extracted$relative" > "$destination/native-path.txt"
cp "$archive.sha256" "$destination/sdk.sha256"
printf '%s/%s\n' "$base" "$archive" > "$destination/sdk-url.txt"
printf 'Checksum-verified SDK extracted. Review its licenses before use. Native directory: %s\n' \
  "$(cat "$destination/native-path.txt")"
