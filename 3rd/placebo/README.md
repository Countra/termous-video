# libplacebo 静态 SDK

本目录只准备原生库及验证程序，不增加公共 Go 色彩处理接口，不修改采集、截图、H.264 或 Core 业务。

## 来源与依赖

`../placebo-lock.json` 固定官方仓库和完整提交。libplacebo 来自
<https://code.videolan.org/videolan/libplacebo>，不从 GitHub 镜像拉取。

| 依赖 | 用途 | 范围 |
|---|---|---|
| libplacebo 7.387.0 | 色彩处理、HDR→SDR 和离屏渲染 | 三平台 |
| glslang 16.6.0 | GLSL→SPIR-V 编译 | 三平台，关闭优化器和命令行程序 |
| SPIRV-Cross | SPIR-V→HLSL／MSL | Windows、macOS |
| Vulkan-Headers | Vulkan 头文件和代码生成注册表 | 三平台；Windows 的 Vulkan stub 也需要头文件 |
| MoltenVK 1.4.2 | Vulkan→系统 Metal | macOS arm64，部署基线 12.0 |
| cereal | MoltenVK 管线缓存序列化 | macOS，仅头文件 |
| fast_float | 浮点文本转换兼容 | 构建时头文件 |
| Jinja 3.1.6、MarkupSafe | 固定模板生成 C 源文件 | 仅构建工具，不进入 SDK |

SPIRV-Cross、Vulkan-Headers、cereal 采用 MoltenVK 1.4.2 的固定依赖提交；生成器和 fast_float 采用 libplacebo 自己固定的提交。不开启 OpenGL、shaderc、LCMS、libdovi、xxhash、demo 或上游测试下载。不需要 FFmpeg。

各静态库分别保存，不合并，也不改写函数或 C++ 符号。libplacebo 当前只有 video 一处依赖；以后若引入另一套同名原生库，需要重新进行共同链接审计。

## 平台与运行时

| 平台 | 编译器和后端 | 运行时要求 |
|---|---|---|
| Windows amd64 | MinGW64 GCC／MSVCRT，D3D11 | 系统 D3D11、DXGI、D3DCompiler 47、UCRT 数学函数；不使用 MSVC |
| Linux amd64 | GCC，Vulkan | 系统 `libvulkan.so.1` 和适用的 GPU 驱动；CI 可用 Mesa 软件 Vulkan |
| macOS arm64 | Apple Clang，静态 MoltenVK | 系统 Metal、Foundation 等框架；不分发 Vulkan／MoltenVK dylib |

这些系统运行时不进入 SDK 或软件分发包。Windows 的 `libplacebo_ucrt_math.a` 是系统 UCRT 数学函数的导入归档，不是第三方 DLL。Windows 验证使用 `-static` 静态链接 GCC/C++/线程运行时；Linux 静态链接 C++ 库，保留系统 C 库；macOS 使用系统 libc++。

MoltenVK 使用本仓库的窄 CMake 配方，保留上游模块划分、Metal 后端和 cereal 缓存。关闭的 SPIRV-Tools 功能仅用于打印反汇编调试文本，不影响实际 SPIR-V→MSL 转换。不会执行其 CPM 自动下载、Xcode 打包或全平台 demo 流程。后续升级需重新核对固定源码列表、平台宏和 CI 链接结果。

MoltenVK 1.4.2 为保留 macOS 12 基线的固定选择，不自动跟随上游替代方案或提高最低系统版本。

## 构建与批准

需要现有 Python 3.12+、CMake 3.24+、Ninja、Git、Meson 1.3+、pkg-config 和对应平台编译器。统一 SDK 构建仍需原有 NASM、LLVM、Go。脚本不安装工具、不改系统 PATH。Jinja／MarkupSafe 使用固定源码的纯 Python 模块，复制到覆盖层中上游生成器实际使用的 `3rdparty/<依赖>/src`；不执行安装器。配置前使用 `python -S` 禁用系统 `site-packages`，校验模块加载位置与模板渲染，不依赖机器预装的 Jinja。

`upstream-review.json` 记录已审查的上游构建文件及生成器摘要。`prepare` 只准备源码；`review` 只输出审查清单位置和摘要；`build` 必须传入已经批准的摘要，核对源码版本和文件内容后才执行。

```text
python 3rd/placebo.py prepare --target windows/amd64
python 3rd/placebo.py review --target windows/amd64
python 3rd/placebo.py build --target windows/amd64 --jobs 8 --accepted-review-sha256 e335368b11c4c48e9d9b45964336cf11679b0adf42814c4a5025afe93987423b
```

独立入口把验证产物保存在 `build/install/placebo/<平台>/verified-*/placebo`，不改变已有 SDK。统一 `3rd/build.py build` 使用相同参数，将组件加入 `sdk/<平台>/placebo/`，与原有两个编解码归档一起验证并事务安装。Linux、macOS 分别使用 `linux/amd64`、`darwin/arm64`，只支持本机构建。

源码、覆盖层、依赖安装前缀、构建输出、日志和测试程序全部留在本仓库 `build` 内。Go 缓存尊重已有 `GOCACHE`／`GOMODCACHE`／`GOTMPDIR`，本工作区继续使用 `TEMP/go`。不改 pnpm 缓存。

覆盖层把 D3D11 的 `spirv-cross-c-shared` 依赖改为静态 `spirv-cross-c`，并将 glslang 绑定到本次安装的三份静态归档；原始源码保持干净。Meson 的静态 `find_library` 不使用 `cpp_link_args` 中的 `-L` 搜索目录，因此这里使用已校验的绝对路径，既避免 macOS 找不到库，也避免意外选中系统安装的同名库或 SPIRV-Tools。libplacebo 配置使用 `--wrap-mode=nodownload` 和显式关闭的可选功能，构建不会自动获取未锁定依赖。

三平台均显式使用锁定的 Vulkan-Headers。Windows 关闭 Vulkan 后端仍会编译 `vulkan/stubs.c`，因此构建不能依赖机器预装头文件；SDK 同时附带 `vulkan/` 和 `vk_video/`，使公开的 `libplacebo/vulkan.h` 可独立编译。这不启用 Windows Vulkan 后端，也不增加 Vulkan 运行时 DLL。

重复构建会刷新 CMake 配置，并重新建立 libplacebo 的 Meson 输出目录，确保当前编译器、静态选项与依赖路径生效；不会沿用旧机器配置。源码下载缓存保留，CMake 依赖的对象产物仍可按构建工具判定复用。

## SDK 内容与验证

组件包含 `lib/`、`include/`、`source-lock.json`、`link.json`、`manifest.json`。`link.json` 给出归档的相对路径、顺序、`PL_STATIC` 编译定义及系统链接参数，不携带构建机器的绝对路径。消费方不需要 Meson、LLVM、Jinja 或上游源码。

组件的完整载荷摘要同时由其自身清单和外层 SDK 清单覆盖。旧的 schema 2 编解码 SDK 仍可完整性审计、编译和测试；重建及发布必须包含新组件。未发布组件前，普通 CI 会明确报告渲染测试未执行；组件存在后不允许因损坏或缺文件而跳过。

构建验证包括：

- C 调用、全归档链接和真实 cgo 编译、执行。
- 统一 SDK 构建还会强制纳入全部 libplacebo 与现有私有 OpenH264／libyuv 归档，检查共存链接和系统动态依赖。
- 合成 RGBA16F scRGB 灰阶（0～1000 nit）与 RGB 色块到 100 nit SDR 的 GPU 离屏渲染、读取及重复运行，检查黑位、亮度顺序、灰阶一致性、颜色通道和 alpha。
- Windows 强制 WARP 保证无独显 runner 也能执行着色器；本地可另运行 `build/checks/placebo/windows/amd64/c.exe --hardware` 验证硬件。
- Linux CI 安装系统 Mesa Vulkan 驱动并执行合成测试，不依赖桌面会话。
- macOS 先独立探测系统 Metal；仅系统没有可用 Metal 设备、且明确设置 `PLACEBO_ALLOW_NO_GPU=1` 时记录 `hdr_render=unavailable`。设备存在时，MoltenVK／libplacebo 初始化、着色器、转换或读取失败均使测试失败，C／cgo 链接和 API 测试始终必需。
- 动态导入白名单和静态归档格式检查；拒绝 SDK 内的 DLL、so、dylib、可执行文件和 thin archive。

结果在 `build/checks/placebo/<平台>/result.json`，详细日志在 `build/logs/placebo-*.log`。cgo 缓存键包含 SDK 头文件和静态库内容摘要，原地更新 SDK 后会重新链接。测试只使用合成数据，不读取桌面，也不创建显示窗口。这证明 SDK 能执行转换，不代表真实 HDR 桌面链路已经修复或完成画质／性能验收。

设备日志写入 stderr，渲染、回读和清理记录执行阶段，避免崩溃时丢失 stdout 缓冲。macOS 若被信号终止，使用系统 `xcrun lldb` 重跑同一合成程序并记录所有线程的调用栈，禁止读取用户 LLDB 初始化文件；诊断限时 60 秒，原失败结果保持不变。调用栈保存到 `build/logs/placebo-*-render-backtrace.log`，由现有 CI 日志步骤上传。设备创建耗时警告不能代替崩溃原因，SIGSEGV 也不能归类为无 GPU。

## CI 发布

沿用 **Build video SDK pull request** 手动触发工作流，三平台从同一提交构建后创建一个 SDK PR，不自动合并。批准摘要固定在工作流中；升级上游文件需要重新审查和批准，禁止自动把刚计算的摘要当作批准。

普通 CI 仍仅在推送到 `main` 时运行，不构建 SDK；使用已提交组件执行 `python scripts/check-placebo.py --allow-missing`。三平台合成渲染结果随手动 SDK 工作流单独上传；macOS 的设备缺失会明确保留为未验证状态。

## 本地验证记录（2026-10-27）

Windows amd64 已使用 MinGW64 GCC 完成静态构建、C／全归档／cgo 调用，以及与现有私有 OpenH264、libyuv 的全归档共同链接。D3D11 WARP 和 NVIDIA GeForce RTX 4060 Ti 均通过三轮合成 scRGB→SDR 渲染；测试确认 D3D11、DXGI、D3DCompiler 47 从 Windows 系统目录加载。动态导入只有系统库，没有 MSYS 或额外的第三方运行时 DLL。

前轮已完成现有视频库的原生测试、race、最终链接回归和三平台编解码 SDK 完整性校验。本轮补齐 Windows Vulkan-Headers 后，重新完成 Windows 组件构建、C／全归档／cgo 链接和 WARP 合成渲染。Python 工具测试运行 65 项，64 项通过，1 项因本机无法创建符号链接而跳过。GLSL 和 Vulkan 源码生成器已在 `python -S` 禁用系统包的条件下执行通过，产物位于 `build/checks/placebo/generators-isolated`。

Linux、macOS 的配方完成静态检查，本机没有这两个平台的运行环境。Linux 生成器修复仍待 CI 完整构建确认。macOS CI 已通过 C／全归档链接及 API 验证，但合成渲染发生 SIGSEGV；现有日志不足以定位根因，已补齐阶段日志与自动调用栈采集，尚不能宣称 macOS 渲染问题已修复。

本机组件产物留在 `build/install/placebo/windows/amd64/verified-*/placebo`；既有 `sdk/` 文件未替换。渲染结果见 `build/checks/placebo/windows/amd64/result.json`，硬件和 WARP 日志分别为 `build/logs/placebo-hardware-render.log`、`build/logs/placebo-c-render.log`。
