# termous-video

Termous 进程内公共视频库，提供 BGRA／I420 转换、缩放、屏幕内容 H.264 编码及 libplacebo HDR→SDR。Go 模块为 `termous/video`；cgo、平台判断和原生资源均封装在库内部，不依赖 Core、RDP、Pion 或采集库。

仓库：<https://github.com/Countra/termous-video>

| 目标 | 工具链 | SDK 目录 |
|---|---|---|
| Windows amd64 | MinGW-w64 GCC，MINGW64/MSVCRT | `sdk/windows/amd64` |
| Linux amd64 | GCC | `sdk/linux/amd64` |
| macOS arm64 | Apple Clang，SDK 12+／Go 1.27 调用端 13+ | `sdk/darwin/arm64` |

每套新版 SDK 包含独立的 `libtermous_video_openh264.a`、`libtermous_video_yuv.a`、头文件、许可证、符号映射和校验清单。第三方符号使用 `termous_video_` 私有前缀，与 RDP／采集库各自的原生依赖隔离。RDP 继续自行构建协议需要的 OpenH264／libyuv，不与本库统一依赖版本。

OpenH264／libyuv 仍分成两个私有静态归档。新增的 `sdk/<系统>/<架构>/placebo/` 独立保存 libplacebo 及其静态依赖，保留原始符号，不参与旧归档的符号改写。不分发第三方 DLL、so、dylib、可执行程序或视频服务。本库没有生产解码接口；解码仅用于测试编码结果。

独立 `color` API 使用已提交的 libplacebo 7.387.0 SDK，按需处理 RGBA16F scRGB。Windows 优先 D3D11 硬件，初始化失败后尝试系统 WARP；Linux 使用系统 Vulkan，macOS 使用静态 MoltenVK 调用系统 Metal。没有自研 CPU 转换或捆绑渲染器；后端不可用时返回明确错误。构建方法和依赖见 [libplacebo 构建说明](3rd/placebo/README.md)。

## 目录

- `3rd/`：全平台 Python 入口、本仓库 CMake 配方、验证程序和测试。
- `build/`：下载的 Git 仓库、编译输出、日志、临时 SDK 和合成画面验证程序，忽略版本控制。
- `sdk/<系统>/<架构>/`：验证通过的安装产物，由 CI 通过 PR 更新。
- `frame/`、`convert/`、`h264/`、`color/`：公共帧合同、转换、编码和色彩处理 API。
- `internal/native/`：薄 C ABI、原生转换／编码及独立的平台链接文件。
- `internal/colornative/`：独立的 libplacebo 设备、纹理渲染与平台链接；只导入 `h264` 不链接此模块或创建设备。
- `scripts/`：消费 SDK 的 Go 测试与二进制依赖检查。

## 使用

```text
python 3rd/check.py
python -B -m unittest discover -s 3rd/tests -v
python scripts/check.py --link --race
python scripts/check-coexist.py --rdp-sdk ../termous-rdp/sdk/windows/amd64
```

`scripts/check.py` 先通过 Go 的构建预演检查三平台 cgo 参数，再执行本机原生测试；参数检查也可单独运行 `python scripts/check-cgo.py`。macOS 的 Go 调用层统一使用 13.0 部署目标，SDK 归档继续兼容 12.0。

最后一条命令使用本机目标对应的 RDP SDK，验证两种链接顺序下入口相互独立且编解码正常；Linux/macOS 请替换 SDK 路径。RDP 的测试入口已自动执行该检查。详细工具链要求、缓存配置和链接说明见 [3rd/README.md](3rd/README.md)。只支持本机构建，不在 Windows 上交叉编译其他平台。

## CI

仅推送到 `main` 分支时自动在三个平台执行工具测试、SDK 完整性检查、关闭 cgo 的测试以及真实原生 Go 测试、race 和链接检查；其他分支推送和 PR 事件不自动触发。普通 CI 不构建 SDK；首次切换私有符号需要先通过手动 SDK 工作流更新产物，旧 schema 1 SDK 无法链接新 Go 库。完整性审计仍可读取旧清单，但原生测试明确拒绝没有私有符号的 SDK。

SDK 构建仅支持手动触发，与 RDP 等仓库保持一致。在 GitHub Actions 中选择 **Build video SDK pull request → Run workflow**，选择工作流分支；可用 `target_branch` 指定已有目标分支，留空时使用所选工作流分支。

手动启动后，三平台从同一源码提交构建，完成普通 C 链接、全归档链接、真实 cgo 链接及合成画面转换/缩放/编码/解码检查后，统一创建 SDK PR。libplacebo 额外验证 FP16 HDR→SDR 离屏渲染；macOS runner 若无 GPU，清单明确记录渲染未验证，仍要求 C／cgo 链接和 API 运行通过。发布过程不自动合并 PR、不覆盖目标分支，目标分支在构建期间推进时会停止发布。

GitHub 仓库需允许 Actions 创建 Pull Request（Settings → Actions → General），发布 job 使用仓库自带 `GITHUB_TOKEN`。其他 job 只有读取权限。

所有运行验证只使用内存中生成的图案，不读取桌面、摄像头或真实用户文件。当前库不包含网络传输、采集、权限或会话业务。

## Go API

```go
encoder, err := h264.New(h264.Config{
    Size: frame.Size{Width: 1280, Height: 720},
    Rate: h264.RateControl{Bitrate: 2_000_000, FPS: 30},
    Level: h264.Level31,
})
if err != nil { return err }
defer encoder.Close()
result, err := encoder.EncodeBGRA(source, h264.Options{Keyframe: true, TimestampMS: 0})
```

调用者计算目标尺寸及单调递增的毫秒时间戳。BGRA 输入支持行填充，I420 输入允许三个平面使用独立步长；默认保留 BT.601 有限范围转换，`Config.Matrix = h264.Matrix709` 显式选择 BT.709。缩放仍为双线性。VUI 标记 BT.709 原色、实际矩阵、sRGB 传递函数和有限范围；`EncodeI420` 的调用方应提供与配置一致的 I420。

编码输出宽高必须为偶数，最小 16×16，最大长边 2560、短边 1440，最高 60fps／24Mbps。`Config.Validate` 和 `UpdateRate` 联合校验尺寸、宏块率、码率及 Level，不能任意拼接独立最大值；`MinimumLevel` 返回满足整个组合的最低等级。独立帧和转换接口仍支持更小或奇数尺寸。编码器不创建观看预设或网络预算。

| 输出组合 | 最低等级（码率仍需单独满足该等级） |
|---|---|
| 720p30／720p60 | 3.1／3.2 |
| 1080p30／1080p60 | 4.0／4.2 |
| 1440p30／1440p60 | 5.0／5.1 |

输入为同步只读借用，调用返回前不得修改或释放；返回的 Annex-B 数据由 Go 持有，后续调用不覆盖。`Skipped` 表示编码器跳帧。转换函数写入调用方提供的缓冲，拒绝输入／输出重叠。编码器的方法内部串行化，关闭等待在途调用结束。

`UpdateRate` 失败会恢复旧配置；若恢复失败，返回 `h264.ErrUnusable`，实例只能关闭。尺寸／Level 变化由调用方创建候选实例并确认首个关键帧后再替换。错误支持 `errors.Is`，公共合同不包含 RDP 错误码。

关闭 cgo 或不支持的平台可以编译 Go API，能力返回不支持。支持平台必须提供私有 SDK 和本机编译器。正式依赖在首个 Go 库版本发布后固定到实际版本；本地通过相邻仓库 workspace，产品构建通过源码锁和临时 modfile 接入，不使用不存在的远程版本。

## HDR 色彩处理

`color.New(color.Options{})` 按需创建设备；`Process(frame.RGBA16F, frame.BGRA)` 同步借用输入和可复用输出，保持尺寸，输出 sRGB／100 nit／全范围 BGRA8。输入为小端 binary16、BT.709 线性 scRGB，**1.0 始终等于 80 nit**。`SDRWhiteNits` 必须是该帧对应的已知桌面白电平（有限正数，最大 10000 nit）；零、未知或会导致派生系数溢出的值返回 `frame.ErrInvalid`。`PeakNits = 0` 仍表示未知显示峰值，该字段不驱动桌面曝光，也不冒充内容 MaxCLL。

固定桌面策略依次执行 `80 / SDRWhiteNits` 白电平归一化、真实 BT.709→BT.2020 线性矩阵变换、libplacebo Mobius 高光压缩及 relative colorimetric 色域映射。输出按 100 nit 计算，GPU 工作值换算为 libplacebo 的 203 nit 单位；拐点为 0.9，固定映射范围为桌面白色的 10 倍，`film_strength=0`。这不是物理显示峰值。动态峰值、自动曝光、局部增强、色域扩张、逆向 HDR 和抖动均关闭。普通白色参考输出约为 249，给高光保留空间。

采用显式采样／自定义参数 Shader／`pl_shader_color_map_ex`／dispatch 单路径，不使用 renderer Hook。合法负 scRGB 分量保留到实际色域转换；未知或不支持必要 LUT 格式的设备明确返回不可用。设备、映射状态、着色器及两个图像纹理复用，白电平只更新动态 uniform；稳态每帧一次图像上传、一次转换派发和一次下载。尺寸或像素越界、NaN／Inf 整帧拒绝。每个处理器串行执行，设备丢失最多重建一次，关闭等待在途调用并可重复调用。转换失败时不得消费目标缓冲。`QueryCapabilities().Compiled` 只说明编译支持，运行后端是否可用由 `New` 判断。

输入步长须按 8 字节像素对齐，输出步长须按 4 字节像素对齐；允许行间填充，最后一行可省略尾部填充。不满足布局要求时在 GPU 传输前返回 `frame.ErrInvalid`，不影响之后的有效帧处理。

合成测试用独立标量公式检查灰阶与高光；`video_native_fixture` 额外检查派发次数、白电平变更时的 Shader 复用，以及同帧无损 PNG／H.264 实际解码。VUI 由编码器自身的原生回归独立检查；跨模块联调测试放在 `color` 包，保持独立 `h264` 包的测试与消费者都不引入 GPU 依赖。设置 `TERMOUS_HDR_FIXTURE_OUTPUT` 可保存合成素材；默认测试不写文件、不采集桌面。基准 `BenchmarkHDRPipeline` 预热 30 帧后报告平均、P95、吞吐及 Go 分配。

`Options.Software` 仅用于 Windows 系统 WARP 验证；Unix 自动模式可以选择系统已有软件 Vulkan。三平台使用相同接口，实际原生运行以对应平台 CI 为准。Windows 合成转换与编码通过不代表真实 HDR 桌面已验收，当前结果见 [1440p／HDR 验证记录](../backend/docs/desktop-video-hdr.md)。

本次迁移的实测结果、体积变化及发布顺序见 [验证记录](docs/integration-validation.md)。
