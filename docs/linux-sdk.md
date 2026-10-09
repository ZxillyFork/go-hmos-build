# Linux Go-HMOS SDK

这是 Linux/amd64 **主机运行**的 Go 工具链，目标平台包括
`openharmony/arm64` 和 `openharmony/amd64`。它不是能在鸿蒙设备上运行的
Go 主机安装包，也不包含 Huawei 商业 SDK、OpenHarmony native SDK、模拟器或凭据。

当前版本化 prerelease：`go1.27.2-hmos.2`。编译器自身版本保持
`go1.27.2-hmos-devel`。核心固定到 `hmos-release-branch.go1.27` 的提交
[`b34856b9da6b50b98c7765b3408c3d097b50867c`](https://github.com/ZxillyFork/go-hmos/commit/b34856b9da6b50b98c7765b3408c3d097b50867c)。
此版本加入异步抢占及抢占信号发送失败后的重试。归档摘要和构建记录见
release 中的 `sdk-manifest.json`；发布工作流通过后提供下载。

## 发布文件

[版本化 release](https://github.com/ZxillyFork/go-hmos-build/releases/tag/go1.27.2-hmos.2)
包含：

- `go1.27.2-hmos-devel.linux-amd64.tar.gz`：单一顶层 `go/`，包含 `bin/go`、
  `bin/gofmt`、`pkg/tool/linux_amd64`、标准库源码、`VERSION`、许可文件。
- `SHA256SUMS`：上述归档及 `provenance.json` 的 SHA-256。
- `provenance.json`：确切核心 SHA、构建仓库 SHA、CI run URL、自举版本、目标列表。
  这是未签名的构建记录，不是密码学认证的供应链证明。
- `sdk-manifest.json`：上述来源信息、归档 URL、SHA-256 和 setup-go 参数。

归档内部还包含 `go/HMOS-SDK.json` 和 `go/core-revision.txt`，方便消费端确认
加载的是预期 fork。归档时间与所有者经过规范化，但不承诺编译产物逐位可重现。
Linux 主机 CI 为 Ubuntu 24.04/amd64；未验证 ARM64 主机发行包。

## 官方 actions/setup-go

当前官方 setup-go v6 的
[`go-download-base-url` 输入](https://github.com/actions/setup-go/blob/924ae3a1cded613372ab5595356fb5720e22ba16/docs/advanced-usage.md#custom-download-url)
可以加载自定义标准 Go 归档。这里使用已核验的确切提交，避免旧版本没有这个输入：

```yaml
env:
  GOENV: 'off'
  GOTOOLCHAIN: local
steps:
  - uses: actions/setup-go@924ae3a1cded613372ab5595356fb5720e22ba16 # v6
    with:
      go-version: '1.27.2-hmos-devel'
      go-download-base-url: 'https://github.com/ZxillyFork/go-hmos-build/releases/download/go1.27.2-hmos.2'
      token: ''
      cache: false
  - name: Verify fork identity
    shell: bash
    run: |
      test "$(go env GOVERSION)" = go1.27.2-hmos-devel
      test "$(cat "$(go env GOROOT)/core-revision.txt")" = b34856b9da6b50b98c7765b3408c3d097b50867c
      go tool dist list | grep -Fx openharmony/arm64
```

不使用 `go-version-file: go.mod` 来选择 fork：普通模块 Go 版本不包含此发行包的
身份。不要使用 `stable`、范围版本、`latest` URL 或允许自动工具链替换。
`cache: false` 关闭模块/构建缓存；setup-go 的工具缓存仍由 action 管理。
它对自定义下载 URL 使用隔离的缓存名，不会复用 stock Go 缓存；自定义下载失败
会失败退出，不会静默转到官方 Go。发布 tag 不覆盖，同一编译器版本的后续构建
必须创建新的 `hmos.N` tag 和 URL。
此固定版本 setup-go 会把 `1.27.2-hmos-devel` 的缓存键规范化为
`1.27.2-hmos`；再次请求完整版本时可能重新下载。这只影响缓存命中率，
不会改变编译器身份或退回 stock Go。

setup-go 没有 SHA-256 输入。需要锁定字节的消费端应在仓库中固定
`sdk-manifest.json` 给出的归档 SHA-256，先下载验证，再运行 setup-go；最后比较
选中工具链与已验证归档里的 `bin/go`、`pkg/tool/linux_amd64/compile` 等文件：

```sh
base=https://github.com/ZxillyFork/go-hmos-build/releases/download/go1.27.2-hmos.2
archive=go1.27.2-hmos-devel.linux-amd64.tar.gz
curl --proto '=https' --proto-redir '=https' --fail --location "$base/$archive" -o "$archive"
# EXPECTED_SHA256 必须是审阅后固定在消费仓库的实际摘要。
printf '%s  %s\n' "$EXPECTED_SHA256" "$archive" | sha256sum --check -
# 以下比较在 setup-go 之后执行，确保选中的工具与已验证的下载一致。
for file in bin/go bin/gofmt pkg/tool/linux_amd64/compile pkg/tool/linux_amd64/asm pkg/tool/linux_amd64/link pkg/tool/linux_amd64/cgo; do
  expected=$(tar -xOzf "$archive" "go/$file" | sha256sum | cut -d' ' -f1)
  actual=$(sha256sum "$(go env GOROOT)/$file" | cut -d' ' -f1)
  test "$actual" = "$expected"
done
```

## 目标交叉编译

Go 工具链本身无需 native SDK 即可运行，但鸿蒙目标使用 libc 和 cgo，最终链接
必须使用另行取得的匹配 SDK。仓库 `scripts/download-sdk.sh` 可下载公开
OpenHarmony 6.1 SDK并校验其官方摘要；它不接受 Huawei 商业条款。
应用使用哪个 SDK/API，应由应用构建要求决定。

```sh
export GOOS=openharmony GOARCH=arm64 CGO_ENABLED=1 GOTOOLCHAIN=local
export OHOS_NDK_HOME=/absolute/path/to/native
export OHOS_TARGET_TRIPLE=aarch64-linux-ohos
# amd64 对应 GOARCH=amd64 和 x86_64-linux-ohos。
cat > "$PWD/ohos-cc" <<'CC'
#!/usr/bin/env bash
set -euo pipefail
exec "$OHOS_NDK_HOME/llvm/bin/clang" --target="$OHOS_TARGET_TRIPLE" --sysroot="$OHOS_NDK_HOME/sysroot" "$@"
CC
chmod +x "$PWD/ohos-cc"
export CC="$PWD/ohos-cc"
go build -trimpath -buildmode=pie -o app .
```

C++ 依赖还需等价的 `CXX` 包装器，调用同 SDK 的 `clang++`。
不要将 `GOOS=linux` 或 `CGO_ENABLED=0` 作为鸿蒙构建的替代。
若产物是 CLI，HDC shell 的网络限制仍可能使它不能联网；普通 HAP 的网络测试
不能证明 shell CLI 在任意设备上可联网。详细差异见 [VALIDATION.md](../VALIDATION.md)。

## 发布验证边界

`Linux Go-HMOS SDK prerelease` 工作流：

1. 校验精确核心 SHA，使用官方 Go 1.27.2 自举并执行既有 host、安全和目标代码生成回归。
2. 打包到标准布局，生成 SHA-256、来源记录；归档排除 VCS、native SDK 和凭据。
3. 在本地只读 HTTP 端点提供候选包，由真正的官方 setup-go 加载。
4. 检查 fork 版本和来源，编译两种目标 runtime，使用公开 native SDK 对两种目标
   构建 PIE/c-shared 并检查架构、解释器和 TLS 重定位。
5. 仅上述检查成功后，以最小 `contents: write` 权限新建 prerelease。
   不覆盖既有 release，不改动核心仓库或官方 release branch。
6. 下载已发布文件核验全部摘要，再由官方 setup-go 加载真实 release URL，
   验证 fork、来源、主机运行和两种目标的 Go/汇编编译。

这条工作流不在目标设备执行产物。先前成功的 x64 debug HAP 验证是独立证据，
见 [应用测试记录](../VALIDATION.md#normal-app-process-network-validation)。
