# 视频依赖构建

## 固定来源

`build-lock.json` 固定官方 Git 仓库和完整提交。video 独立维护依赖版本，不要求与 RDP 或采集库一致：

- OpenH264 2.6.0：`652bdb7719f30b52b08e506645a7322ff1b2cc6f`。
- libyuv：`eeb06a6451ba2e21f8ff272c7b42fc62b9faecc5`。

`prepare` 只下载并检出源码；已有来源被修改时拒绝覆盖。`build` 只验证并使用已有源码，不隐式下载。构建使用本仓库的 CMake 配方和固定编译单元清单，不执行下载源码中的 Makefile、CMakeLists、版本生成脚本或依赖安装器。

OpenH264 保留 x64 NASM / ARM64 NEON；libyuv 保留 x64 SIMD 和 ARM64 NEON 分派，禁用 JPEG 依赖，Apple Silicon 不编译 SVE/SME 内核。更新依赖时需重新核对源文件清单、架构宏和合成画面测试。

## 工具链

通用要求：Python 3.12+、Git、CMake 3.20+、Ninja、Go 1.27.1、LLVM 18+ 的 `llvm-nm` 和 `llvm-objcopy`。LLVM 只处理 SDK 归档和符号，普通 Go 调用方不需要安装它；可通过 `LLVM_NM` / `LLVM_OBJCOPY` 指定工具路径。

- Windows：MSYS2 **MINGW64** 的 GCC/G++、CMake、Ninja、NASM 和 Python；或已有同 ABI 工具链的 PowerShell 环境。不要使用 MSVC、clang-cl、UCRT64 或 MSYS GCC。
- Linux：GCC/G++、NASM。只需系统开发工具，不需要 X11、音频或桌面采集依赖。
- macOS：Apple Clang / Xcode Command Line Tools，ARM64 原生宿主。部署基线固定为 macOS 12。

macOS 的符号工具使用 Homebrew LLVM，CI 显式设置 `LLVM_NM` 和 `LLVM_OBJCOPY` 为 `$(brew --prefix llvm)/bin/` 下的对应工具。手动构建时也可如此指定，避免选中 Xcode 自带的旧版同名工具；编译器仍由 `xcrun` 选择 Apple Clang。脚本在编译前校验并固定符号工具的绝对路径，后续 PATH 调整不会改变选择。

先将工具加入当前终端 PATH，也可用 `CC` / `CXX` 指定现有编译器。脚本不安装工具、不修改系统 PATH。

```text
python 3rd/build.py prepare --target windows/amd64
python 3rd/build.py build --target windows/amd64 --jobs 8
python 3rd/sdk.py verify --sdk-dir sdk/windows/amd64 --target windows/amd64
python 3rd/sdk.py audit
```

Linux / macOS 分别使用 `linux/amd64`、`darwin/arm64`，也可以省略 `--target` 自动检测宿主。

`verify` 验证指定 SDK 与当前源码配方一致；`audit` 校验已有 SDK 的完整性、固定来源与验证记录，允许源码升级后尚未重新生成 SDK。两者都会拒绝文件损坏、缺失和非法清单。`audit` 通过不代表已有 SDK 已按最新配方重建。

本工作区的 Go 缓存继续设置为：

```text
GOCACHE=D:/Item/vibe_coding/termous/TEMP/go/build
GOMODCACHE=D:/Item/vibe_coding/termous/TEMP/go/mod
GOTMPDIR=D:/Item/vibe_coding/termous/TEMP/go/tmp
```

已有 Go 缓存配置优先使用；CI 等未配置环境默认放入 `build/cache/go`。其余源码、原生缓存、日志和验证产物全部位于本仓库 `build`。不涉及 pnpm 缓存。

## 验证与安装

构建顺序：验证源码 → 配置与编译 → 临时安装 → 私有符号隔离 → C / 全归档 / cgo 链接 → 合成画面运行 → 动态依赖检查 → 生成清单 → 替换 SDK。旧 SDK 在新版本通过检查前保持可用，目录替换失败时恢复旧目录；存在遗留备份时停止并报告，不自动删除。

隔离工具读取两个归档自身定义的外部符号，生成确定性的 `symbols/rename.map`，将定义和内部引用统一改写为 `termous_video_` 前缀，系统及运行时的外部引用保持原名。C 接口映射写入 `include/termous_video_symbols.h`，必须在第三方头文件之前包含。两个独立归档分别安装为 `libtermous_video_openh264.a`、`libtermous_video_yuv.a`，不合并，未隔离产物仅留在构建缓存。schema 2 清单记录隔离规则版本、工具版本、符号数量和文件摘要。

Windows 在 LLVM 改写后归零 COFF 未初始化数据段的文件偏移，保留段大小及归档布局，避免 GNU 链接器将整段 BSS 写进 EXE。安装验证、公共 Go 链接验证和最终 RDP worker 检查均拒绝 BSS 落盘，防止符号隔离造成异常体积增长。

构建前后核对配方摘要，即使开始时工作区已有修改，也不能把构建期间变化后的配方记为产物来源。CMake 同时核对宿主系统、架构和 C/C++ 工具链，拒绝错误目标。工具探测限时 60 秒，单条构建命令限时 30 分钟，合成验证程序限时 30 秒；失败时保留日志，不安装未完成验证的产物。

`checks/cgo_main.go.in` 仅用于构建时验证，复制到 `build/checks/<目标>/cgo` 的独立临时 Go 模块，不是产品 API。合成测试使用 libyuv 转换和缩小图案，再经 OpenH264 编码/解码核对输出尺寸与内容。

静态库供 C/cgo 调用仍需要链接 C++ 运行时。常用链接顺序为：

```text
Windows: libtermous_video_openh264.a libtermous_video_yuv.a -static -lstdc++ -lwinpthread
Linux:   libtermous_video_openh264.a libtermous_video_yuv.a -Wl,-Bstatic -lstdc++ -Wl,-Bdynamic -pthread -lm
macOS:   libtermous_video_openh264.a libtermous_video_yuv.a -mmacosx-version-min=12.0 -lc++
```

不保证系统运行库也完全静态链接；验证拒绝额外 OpenH264/libyuv 动态库及 Windows MSVC/MSYS/MinGW 运行时 DLL。

## 发布与后续集成

CI 固定来源提交，将每个文件 SHA256、依赖锁、配方摘要、工具链和验证结果记录在 `manifest.json`。发布 job 验证全部平台、来源一致性和目录范围后，用 `git commit -F` 提交 SDK 到独立分支并创建 PR。测试中的 Git/GitHub 操作均使用模拟，不创建真实 PR。

本机未提交源码构建会明确记录 `source_dirty`，不能作为 CI 发布产物。源码推送后，在 GitHub Actions 手动运行 **Build video SDK pull request** 才会构建和提交 SDK PR；仅推送到 `main` 分支时自动执行工具测试、已有 SDK 完整性检查、公共 Go API 测试、race 和原生链接检查，其他分支推送和 PR 事件不自动触发。普通 CI 不构建 SDK，本地脚本不会自动提交或推送。公共 Go 库要求 schema 2 私有 SDK，迁移时必须先手动生成并合入新的 SDK PR。

RDP 及采集库继续维护自己的依赖；video 私有符号与它们隔离，不依赖链接顺序或相同版本。组合产物仍需验证真实链接、动态依赖和合成画面，符号审计不能替代对应平台的运行验证。本轮 RDP 同步移除 Intel Mac，只保留与 video 一致的三个目标。
