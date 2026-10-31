# 视频依赖构建

## 固定来源

`build-lock.json` 固定官方 Git 仓库和完整提交。video 独立维护依赖版本，不要求与 RDP 或采集库一致：

- x264 build 165：官方 `https://code.videolan.org/videolan/x264.git`，固定提交 `0480cb05fa188d37ae87e8f4fd8f1aea3711f7ee`。
- OpenH264 2.6.0：官方 `https://github.com/cisco/openh264.git`，固定提交 `652bdb7719f30b52b08e506645a7322ff1b2cc6f`。
- libyuv：`eeb06a6451ba2e21f8ff272c7b42fc62b9faecc5`。

`prepare` 只下载并检出源码；已有来源被修改时拒绝覆盖。`build` 只验证并使用已有源码，不隐式下载。x264／OpenH264／libyuv 使用本仓库的 CMake 配方和固定编译单元清单，不执行它们的上游构建脚本。

libplacebo 使用独立的 `placebo-lock.json` 和已审查的固定版本上游构建入口，执行前校验 `placebo/upstream-review.json` 的批准摘要；不是自动批准下载内容。具体依赖、后端、静态链接和验证边界见 [libplacebo 构建说明](placebo/README.md)。统一 SDK 安装仍是单次事务，任何必需检查失败都不会替换旧 SDK。

x264 固定 8-bit、4:2:0、逐行编码，启用平台线程与 x64 NASM / ARM64 NEON；不构建 CLI、OpenCL、10-bit 或 SVE/SVE2；libyuv 保留 x64 SIMD 和 ARM64 NEON 分派，禁用 JPEG 依赖，Apple Silicon 不编译 SVE/SME 内核。OpenH264 编译完整 common、encoder、decoder、processing 及平台 SIMD，不构建命令行程序。更新依赖时需重新核对源文件清单、架构宏和合成画面测试。

## 当前实施边界

构建、安装、artifact 和 SDK PR 统一使用 `sdk/<目标>/`（schema 4），包含 x264、完整 OpenH264、libyuv 和原有 libplacebo 组件。现存 SDK 文件保留到 CI 成套重建后替换，不建立并行过渡目录。OpenH264 同时提供编码与解码能力，本阶段主要用于解码 x264 合成输出；后续生产编码仍迁移至 x264。

本阶段只验证依赖 SDK。Go/C 生产编码适配尚未迁移，其原生编译与运行测试不作为当前 CI 的通过条件；不保证新 SDK 能被旧适配调用。三平台产物合并并就绪后，再替换编码适配和编码解码测试。RDP 自身的 OpenH264 不属于迁移范围。

## 工具链

通用要求：Python 3.12+、Git、CMake 3.24+、Ninja、Meson 1.3+、pkg-config、Go 1.27.1、LLVM 18+ 的 `llvm-nm` 和 `llvm-objcopy`。LLVM 只处理 SDK 归档和符号，普通 Go 调用方不需要安装它；可通过 `LLVM_NM` / `LLVM_OBJCOPY` 指定工具路径。

- Windows：MSYS2 **MINGW64** 的 GCC/G++、CMake、Ninja、NASM 和 Python；或已有同 ABI 工具链的 PowerShell 环境。不要使用 MSVC、clang-cl、UCRT64 或 MSYS GCC。
- Linux：GCC/G++、NASM；libplacebo 合成测试还需要系统 Vulkan loader 和可用驱动，CI 使用 Mesa 软件 Vulkan。不需要 X11、音频或桌面采集依赖。
- macOS：Apple Clang / Xcode Command Line Tools，ARM64 原生宿主。部署基线固定为 macOS 12。

macOS 的符号工具使用 Homebrew LLVM，CI 显式设置 `LLVM_NM` 和 `LLVM_OBJCOPY` 为 `$(brew --prefix llvm)/bin/` 下的对应工具。手动构建时也可如此指定，避免选中 Xcode 自带的旧版同名工具；编译器仍由 `xcrun` 选择 Apple Clang。脚本在编译前校验并固定符号工具的绝对路径，后续 PATH 调整不会改变选择。

先将工具加入当前终端 PATH，也可用 `CC` / `CXX` 指定现有编译器。脚本不安装工具、不修改系统 PATH。

```text
python 3rd/build.py prepare --target windows/amd64
python 3rd/build.py build --target windows/amd64 --jobs 8 --accepted-review-sha256 e335368b11c4c48e9d9b45964336cf11679b0adf42814c4a5025afe93987423b
python 3rd/sdk.py verify --sdk-dir sdk/windows/amd64 --target windows/amd64
python 3rd/sdk.py audit
```

Linux / macOS 分别使用 `linux/amd64`、`darwin/arm64`，也可以省略 `--target` 自动检测宿主。

仅在本地验证、不安装SDK 产物时，为 `build` 增加 `--staging-only`，完整 SDK 会保存在 `build/install/<目标>/verified-*` 并打印路径。该目录中的清单也可用 `verify` 检查。

`verify` 严格校验指定 SDK 与当前配方一致；`audit` 校验已安装三平台 SDK 的完整性、来源一致性及运行记录，允许同代 SDK 的配方稍早于源码。旧清单不作为有效 SDK 接受。`python 3rd/sdk.py check --sdk-dir <SDK目录>` 对本机 SDK 执行编码、跨库解码、渲染和链接检查，省略目录时使用 `sdk/<目标>`。

普通 CI 的 `--allow-unbuilt` 只在三个目标都是完整且来源一致的同代旧产物（schema 2 或 schema 3）时报告待重建，不运行旧原生检查。旧产物仍核对文件摘要、归档集合与格式、必要头文件、许可证、依赖锁及 libplacebo 子组件；整个 SDK 缺失、缺平台、新旧混用、文件损坏或跨代产物不允许跳过。手动 SDK 工作流不使用该选项，所有新产物必须完成严格校验。

本工作区的 Go 缓存继续设置为：

```text
GOCACHE=D:/Item/vibe_coding/termous/TEMP/go/build
GOMODCACHE=D:/Item/vibe_coding/termous/TEMP/go/mod
GOTMPDIR=D:/Item/vibe_coding/termous/TEMP/go/tmp
```

已有 Go 缓存配置优先使用；CI 等未配置环境默认放入 `build/cache/go`。其余源码、原生缓存、日志和验证产物全部位于本仓库 `build`。不涉及 pnpm 缓存。

## 验证与安装

构建顺序：验证源码和上游脚本批准摘要 → 配置与编译 → 临时安装 → 编解码依赖私有符号隔离 → C / 全归档 / cgo 链接 → 合成画面运行 → libplacebo 组件构建与测试 → 动态依赖检查 → 生成清单 → 替换SDK。旧 SDK 在新版本通过检查前保持可用，目录替换失败时恢复旧目录；存在遗留备份时停止并报告，不自动删除。

隔离工具读取三个归档自身定义的外部符号，生成确定性的 `symbols/rename.map`，将定义和内部引用统一改写为 `termous_video_` 前缀，系统及运行时的外部引用保持原名。C 接口映射写入 `include/termous_video_symbols.h`，必须在第三方头文件之前包含。三个独立归档分别安装为 `libtermous_video_x264.a`、`libtermous_video_yuv.a`、`libtermous_video_openh264.a`，不合并，未隔离产物仅留在构建缓存。schema 4 清单记录隔离规则版本、工具版本、符号数量和文件摘要。

Windows 在 LLVM 改写后归零 COFF 未初始化数据段的文件偏移，保留段大小及归档布局，避免 GNU 链接器将整段 BSS 写进 EXE。安装验证、公共 Go 链接验证和最终 RDP worker 检查均拒绝 BSS 落盘，防止符号隔离造成异常体积增长。

构建前后核对配方摘要，即使开始时工作区已有修改，也不能把构建期间变化后的配方记为产物来源。CMake 同时核对宿主系统、架构和 C/C++ 工具链，拒绝错误目标。工具探测限时 60 秒，单条构建命令限时 30 分钟，合成验证程序限时 30 秒；失败时保留日志，不安装未完成验证的产物。

`checks/cgo_main.go.in` 仅用于构建时验证，复制到 `build/checks/<目标>/cgo` 的独立临时 Go 模块，不是产品 API。合成测试使用 libyuv 转换动态图案，运行 x264 1／8 线程编码，核验 Constrained Baseline Level 5.1 SPS、Annex B NAL、SPS/PPS/IDR、连续输出时间戳、无延迟帧、100→50 Mbps 参数重配及强制关键帧。测试按编码场景、素材、解码校验和入口拆分。每段编码序列由同一个 OpenH264 解码器连续解码，使用同步单线程（线程选项为 0），关闭错误掩盖，核对尺寸、平面、步长、时间戳和帧数，并检查结束后无残留帧。色块内部对独立标量 BT.601 参考的 Y/U/V 误差不得超过 8 个八位量化级。

SDK 还检查 OpenH264 编解码对象初始化、释放和版本 API，并单独运行只链接 x264／libyuv 的编码程序。只有全部运行成功，清单才记录 `x264_encode=true`、`encoder_only_link=true`、`video_decode=true`、`decoder=openh264`、`openh264_api=true`。这些结果不替代浏览器／Android 客户端解码或真实 2K60 性能验收。

静态库供 C/cgo 调用仍需要链接 C++ 运行时。常用链接顺序为：

```text
Windows: libtermous_video_x264.a libtermous_video_yuv.a -static -lstdc++ -lwinpthread
Linux:   libtermous_video_x264.a libtermous_video_yuv.a -Wl,-Bstatic -lstdc++ -Wl,-Bdynamic -pthread -lm
macOS:   libtermous_video_x264.a libtermous_video_yuv.a -mmacosx-version-min=12.0 -lc++
```

以上为纯 x264 编码链接；跨库解码测试在系统链接参数之前额外加入 `libtermous_video_openh264.a`，不依赖相邻 RDP SDK。所有依赖头文件之前仍需包含 `termous_video_symbols.h`。

不保证系统运行库也完全静态链接；验证拒绝额外 x264/OpenH264/libyuv 动态库及 Windows MSVC/MSYS/MinGW 运行时 DLL。

## 发布与后续集成

CI 固定来源提交，将每个文件 SHA256、依赖锁、配方摘要、工具链和验证结果记录在 `manifest.json`。发布 job 验证全部平台、来源一致性和目录范围后，用 `git commit -F` 提交 SDK 到独立分支并创建 PR。测试中的 Git/GitHub 操作均使用模拟，不创建真实 PR。

本机未提交源码构建会明确记录 `source_dirty`，不能作为 CI 发布产物。源码推送后，在 GitHub Actions 手动运行 **Build video SDK pull request** 才会构建和提交 SDK PR。仅推送到 `main` 时自动执行构建工具测试、无 cgo 测试和已发布 SDK 的原生验证；其他分支推送和 PR 事件不自动触发。普通 CI 不重建 SDK，本地脚本不会自动提交或推送。上层原生 Go API 测试需在后续编码适配迁移后恢复，SDK 的独立 cgo 检查不代替产品 API 验证。

RDP 及采集库继续维护自己的依赖；video 私有符号与它们隔离，不依赖链接顺序或相同版本。组合产物仍需验证真实链接、动态依赖和合成画面，符号审计不能替代对应平台的运行验证。本次不修改 RDP 构建与依赖。
