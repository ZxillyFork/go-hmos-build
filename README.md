# go-hmos-build

独立的 [go-hmos](https://github.com/ZxillyFork/go-hmos) 构建和验证仓库。
Go 核心仓库只保留移植代码、测试和平台文档；GitHub Actions、SDK 下载及
构建包装脚本放在这里。安装器位于独立的
[go-hmos-installer](https://github.com/ZxillyFork/go-hmos-installer) 仓库。

**移植仍是实验性的。交叉编译成功不代表已在 OpenHarmony 或 HarmonyOS NEXT
设备上运行。** 当前已完成和未完成的验证分别记录在 [VALIDATION.md](VALIDATION.md)。
目标平台限制见核心仓库的
[平台说明](https://github.com/ZxillyFork/go-hmos/blob/feature/openharmony-go1.27/doc/openharmony.md)。

## 当前源代码固定状态

初始仓库暂不固定核心提交，等待独立 `runtime.GOOS = "openharmony"` 身份修改完成。
因此默认推送只运行离线脚本自测，不会用旧提交构建，也不会将跳过的核心检查算作通过。
手动构建现在必须填写审查过的完整 `core_sha`。确认最终核心提交后，将它写入
`source.json`，默认 host 检查随即启用；SDK 检查仍需明确选择 `sdk=true`。

## GitHub Actions

[OpenHarmony build and checks](https://github.com/ZxillyFork/go-hmos-build/actions/workflows/openharmony.yml)
提供以下检查：

- 推送或拉取请求：离线脚本测试、Linux/amd64 三阶段工具链 bootstrap、构建标签、
  ARM64/AMD64 TLS 代码生成、Go API、命令驱动测试，以及两个目标的 runtime
  Go/汇编编译。
- 手动运行并选择 `sdk=true`：另外下载官方公开 OpenHarmony 6.1 SDK，校验官方
  SHA-256，使用真实 SDK 对 ARM64 和 AMD64 编译、外部链接并检查 ELF。
  下载约 2.3 GB，需要额外解压空间。这个检查不会启动设备或模拟器。
- SDK 输出包括 c-shared、c-archive、PIE、dlopen/pthread loader、netgo 变体、
  runtime / os/signal / runtime/pprof / net / time / crypto/x509 测试二进制，
  以及目标平台的 go、gofmt 和编译工具。失败时保留已有产物供排查。

`source.json` 固定默认 Go 核心提交。手动运行可填写 `core_sha`，只接受
`ZxillyFork/go-hmos` 中的完整小写 40 位提交 SHA，不接受会移动的分支或标签。
每个构建任务在 bootstrap 前再次核对 checkout 的实际 SHA。测试其他提交前请先
审查其代码；构建源代码本身会执行该提交中的程序。

工作流仅请求 `contents: read`，checkout 不保留凭据，不创建令牌、不发布 release，
也不修改核心仓库。Actions 固定到已核验的具体提交。工具链使用官方 Go 1.27.1
bootstrap，关闭 setup-go 构建缓存；bootstrap、host test、每个 SDK 架构分别使用
不同的 GOCACHE。host 检查同时验证 fork 的开发版 build ID，并回归测试与上游
bootstrap 共用缓存的情况。

## 本地复现

需要 Linux/amd64、Bash、Python 3、Git、官方 Go 1.27.1，以及本机 C 编译器。
SDK 检查还需要 curl、GNU tar、unzip 和 sha256sum。脚本不负责安装软件或接受
SDK 的点击确认条款；使用前请阅读 SDK 随附许可。

```sh
git clone https://github.com/ZxillyFork/go-hmos-build.git
cd go-hmos-build
git clone https://github.com/ZxillyFork/go-hmos.git source
# source.json 尚未固定时，先设置 CORE_SHA 为审查过的完整 40 位核心提交。
# 固定后可省略 CORE_SHA。
core_sha=$(python3 scripts/source-pin.py --revision "${CORE_SHA:-}") || exit 1
git -C source checkout --detach "$core_sha"
export GO_SOURCE_ROOT="$PWD/source"
export GOROOT_BOOTSTRAP="$(go env GOROOT)"
bash scripts/bootstrap.sh
bash scripts/test-host.sh
```

从已有 checkout 构建时，设置 `GO_SOURCE_ROOT` 为其绝对路径。请记录实际提交和
是否存在本地修改；只有工作流中的 checkout 会自动核对指定提交。
脚本忽略持久化 `go env` 配置及继承的 GOOS、GOARCH、GOFLAGS、GOEXPERIMENT，
避免无意中把本机检查变成交叉编译。bootstrap 编译器与源码 checkout 必须分开。

SDK 检查可使用已取得的官方 SDK：

```sh
export OHOS_NDK_HOME=/absolute/path/to/sdk/native
GOARCH=arm64 BUILD_NATIVE_TOOLS=1 bash scripts/build.sh
GOARCH=amd64 BUILD_NATIVE_TOOLS=1 bash scripts/build.sh
```

或者显式下载公开 SDK：

```sh
export SDK_DOWNLOAD_DIR="$(mktemp -d)"
bash scripts/download-sdk.sh
export OHOS_NDK_HOME="$(cat "$SDK_DOWNLOAD_DIR/native-path.txt")"
GOARCH=arm64 BUILD_NATIVE_TOOLS=1 bash scripts/build.sh
GOARCH=amd64 BUILD_NATIVE_TOOLS=1 bash scripts/build.sh
```

下载器只使用官方公开地址，经 SHA-256 验证后解压 Linux native 包，支持 clang
符号链接。它拒绝覆盖已解压的 SDK，并在结束时删除自己创建的大型临时压缩包。
官方校验文件在下载时取得，**并非仓库内固定的历史摘要**；下载后的原始摘要和
URL 随产物保留，以便核对这一次使用的 SDK。不会改用未校验的镜像或本机假 sysroot。
此 SDK 是公开 OpenHarmony SDK，不等同于 Huawei 商业 HarmonyOS NEXT SDK。

默认产物目录为 `openharmony-out/<arch>/`；可用 `OUT_DIR` 指定其它目录。
`GO_HMOS_CACHE_ROOT` 可调整缓存目录，默认 `.cache/`。
上述原生工具是交叉编译产物，不是完整安装包；它们尚未证明能在目标设备上执行、
自举或通过完整标准库测试。请勿把 CI 工件直接标作已验证的发行版。

## 检查脚本

```sh
for script in scripts/*.sh; do bash -n "$script"; done
python3 -m unittest discover -s tests -v
```

离线测试使用明确标注的模拟 SDK 压缩包来检查下载器控制流、校验失败、clang
符号链接和缺失工具处理。它们不进行真实 SDK 编译，也不计作目标平台验证。

## 真实设备验证

本仓库只构建。真机、完整系统模拟器、签名 HAP/N-API 集成、生命周期、网络策略、
证书服务、时区同步和内存压力等仍需单独验证。运行时应记录 OS/API/SDK/CPU、
核心提交、命令、退出码和日志；编译通过、未运行和运行失败必须分别报告。
详见 [验证记录](VALIDATION.md) 与核心平台文档。

## License

BSD 3-Clause，见 [LICENSE](LICENSE)。源自 Go 项目的脚本保留原有版权声明；SDK
本身按其随附许可分发和使用，本仓库不重新分发 SDK。
