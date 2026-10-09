# go-hmos-build

独立的 [go-hmos](https://github.com/ZxillyFork/go-hmos) 构建和验证仓库。
Go 核心仓库只保留移植代码、测试和平台文档；GitHub Actions、SDK 下载及
构建包装脚本放在这里。安装器位于独立的
[go-hmos-installer](https://github.com/ZxillyFork/go-hmos-installer) 仓库。

**移植仍是实验性的。交叉编译成功不代表已在 OpenHarmony 或 HarmonyOS NEXT
设备上运行。** 当前已完成和未完成的验证分别记录在 [VALIDATION.md](VALIDATION.md)。
目标平台限制见核心仓库的
[平台说明](https://github.com/ZxillyFork/go-hmos/blob/b637b8617624655906b737977f50de5280bf7f65/doc/openharmony.md)。

## 当前源代码固定状态

默认核心提交为 [b637b8617624](https://github.com/ZxillyFork/go-hmos/commit/b637b8617624655906b737977f50de5280bf7f65)，
基于官方 Go 1.27.2，保留前两轮 review 后的 OpenHarmony、TLS、栈元数据和
ELF note 修复，并使用独立的 `runtime.GOOS = "openharmony"` 身份。
工具版本为 `go1.27.2-hmos-devel`，保留独立的内容 build ID。

本次导入旧上游基线之后的全部 10 项安全修复，并新增对应的主机回归、
HTTP/2 race 检查和安装器原生 Windows junction 回归。

安装器现提供独立的版本命令 `go1.27.2-hmos`：

```sh
go install github.com/ZxillyFork/go-hmos-installer/go1.27.2-hmos@latest
go1.27.2-hmos download
```

它固定该核心提交，可与官方 `go1.27.2` helper 并存；旧安装器根入口仍保留
原版本。最终安装器的 Linux/macOS/Windows 与最低 Go CI 均已通过，详见
[安装器验证](VALIDATION.md#versioned-installer)。
该精确提交已通过 [host 与官方 SDK 检查](https://github.com/ZxillyFork/go-hmos-build/actions/runs/37872123883)，
覆盖 ARM64 和 AMD64。详细结果、已核验工件及安装器更新状态见
[VALIDATION.md](VALIDATION.md)。SDK 编译/链接/ELF 检查**不等于目标设备执行**。
默认推送运行 host 检查；真实 SDK 检查需手动选择 `sdk=true`。

## GitHub Actions

[OpenHarmony build and checks](https://github.com/ZxillyFork/go-hmos-build/actions/workflows/openharmony.yml)
提供以下检查：

- 推送或拉取请求：离线脚本测试、Linux/amd64 三阶段工具链 bootstrap、构建标签、
  ARM64/AMD64 TLS 代码生成、Go API、命令驱动测试，以及两个目标的 runtime
  Go/汇编编译；另执行 Go 1.27.2 相关安全回归及 HTTP/2 race 检查。
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
也不修改核心仓库。Actions 固定到已核验的具体提交。工具链使用官方 Go 1.27.2
bootstrap，关闭 setup-go 构建缓存；bootstrap、host test、每个 SDK 架构分别使用
不同的 GOCACHE。host 检查同时验证 fork 的开发版 build ID，并回归测试与上游
bootstrap 共用缓存的情况。

## 本地复现

需要 Linux/amd64、Bash、Python 3、Git、官方 Go 1.27.2，以及本机 C 编译器。
SDK 检查还需要 curl、GNU tar、unzip 和 sha256sum。脚本不负责安装软件或接受
SDK 的点击确认条款；使用前请阅读 SDK 随附许可。

```sh
git clone https://github.com/ZxillyFork/go-hmos-build.git
cd go-hmos-build
git clone https://github.com/ZxillyFork/go-hmos.git source
# 默认使用 source.json；CORE_SHA 可显式选择另一个审查过的完整 40 位提交。
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

### 官方 x64 模拟器实验

`HarmonyOS x64 emulator runtime` 工作流在 `ci/harmonyos-amd64` 分支推送时运行，
也可手动触发。它只使用 GitHub 的 Ubuntu 24.04 x64 runner 和实际 KVM，
从华为 CDN 下载固定 SHA-256 的 Command Line Tools 26.0.0.821，
由官方 CLI 下载 HarmonyOS 6.1.1（API 24）PC 镜像。ARM 暂不测试。
这与用于编译的公开 OpenHarmony 6.1（API 23）SDK 是不同组件；兼容性由
实际执行结果判断，不把 API 版本不同藏在同一个 SDK 标签里。

流程先检查 KVM 能否创建 VM，再检查下载、许可、镜像、启动、HDC 传输、
ABI、Go runtime 和选定标准库测试。每个 guest 命令都有随机退出码标记，
HDC 返回零但设备断连、缺少标记或 guest 非零退出均不能算成功。
启动、下载和每项测试均有超时，并在退出时收集日志、停止该模拟器实例。
测试包括 hello 的真实 GOOS/GOARCH、GC、goroutines、timers、OS threads、
cgo/C TLS、foreign pthread callbacks、dlopen、netgo 变体和本机网络。
标准库的精确选择见 `testdata/emulator/stdlib-tests.tsv`，不等同于完整 Go test suite。

CLI 的来源线索参考了 [cjv 的实验分支](https://github.com/Zxilly/cjv/tree/60759572e197520477d814b2382a6753e95fa44f)，
实现与测试在本仓库独立维护。`scripts/emulator/cli.json` 保留下载地址、
固定摘要和来源。摘要已与此前成功下载的记录相符，不能描述成已独立取得
华为签名的 checksum。镜像由官方工具安装，日志记录实际 system.img 摘要，
目前不声称镜像已被仓库内历史摘要固定。

此前同一包的协议已在 [已有 cjv 流程](https://github.com/Zxilly/cjv/actions/runs/37875586125)
接受；本流程在重新接受之前核对完整协议文本的摘要。新增或变更协议会停止，
不自动沿用旧授权。不会修改 KVM 设备权限或永久组成员关系，不上传或缓存
华为 SDK、CLI 和系统镜像。工件仅包含测试程序及诊断；脚本单元测试也不计作
目标系统执行。最新实际结果以精确提交的 Actions 日志及 `VALIDATION.md` 为准。

真机、签名 HAP/N-API 集成、生命周期、网络策略、
证书服务、时区同步和内存压力等仍需单独验证。运行时应记录 OS/API/SDK/CPU、
核心提交、命令、退出码和日志；编译通过、未运行和运行失败必须分别报告。
详见 [验证记录](VALIDATION.md) 与核心平台文档。

## License

BSD 3-Clause，见 [LICENSE](LICENSE)。源自 Go 项目的脚本保留原有版权声明；SDK
本身按其随附许可分发和使用，本仓库不重新分发 SDK。
