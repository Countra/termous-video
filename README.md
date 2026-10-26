# termous-video

Termous 进程内公共视频库，提供 BGRA／I420 转换、缩放和屏幕内容 H.264 编码。Go 模块为 `termous/video`；cgo、平台判断和原生资源均封装在库内部，不依赖 Core、RDP、Pion 或采集库。

仓库：<https://github.com/Countra/termous-video>

| 目标 | 工具链 | SDK 目录 |
|---|---|---|
| Windows amd64 | MinGW-w64 GCC，MINGW64/MSVCRT | `sdk/windows/amd64` |
| Linux amd64 | GCC | `sdk/linux/amd64` |
| macOS arm64 | Apple Clang，SDK 12+／Go 1.27 调用端 13+ | `sdk/darwin/arm64` |

每套新版 SDK 包含独立的 `libtermous_video_openh264.a`、`libtermous_video_yuv.a`、头文件、许可证、符号映射和校验清单。第三方符号使用 `termous_video_` 私有前缀，与 RDP／采集库各自的原生依赖隔离。RDP 继续自行构建协议需要的 OpenH264／libyuv，不与本库统一依赖版本。

SDK 仍分成两个静态归档，不分发 DLL、可执行程序或视频服务。本库没有生产解码接口；解码仅用于测试编码结果。

## 目录

- `3rd/`：全平台 Python 入口、本仓库 CMake 配方、验证程序和测试。
- `build/`：下载的 Git 仓库、编译输出、日志、临时 SDK 和合成画面验证程序，忽略版本控制。
- `sdk/<系统>/<架构>/`：验证通过的安装产物，由 CI 通过 PR 更新。
- `frame/`、`convert/`、`h264/`：公共帧合同、转换和编码 API。
- `internal/native/`：薄 C ABI、原生转换／编码及独立的平台链接文件。
- `scripts/`：消费 SDK 的 Go 测试与二进制依赖检查。

## 使用

```text
python 3rd/check.py
python -B -m unittest discover -s 3rd/tests -v
python scripts/check.py --link --race
python scripts/check-coexist.py --rdp-sdk ../termous-rdp/sdk/windows/amd64
```

最后一条命令使用本机目标对应的 RDP SDK，验证两种链接顺序下入口相互独立且编解码正常；Linux/macOS 请替换 SDK 路径。RDP 的测试入口已自动执行该检查。详细工具链要求、缓存配置和链接说明见 [3rd/README.md](3rd/README.md)。只支持本机构建，不在 Windows 上交叉编译其他平台。

## CI

仅推送到 `main` 分支时自动在三个平台执行工具测试、SDK 完整性检查、关闭 cgo 的测试以及真实原生 Go 测试、race 和链接检查；其他分支推送和 PR 事件不自动触发。普通 CI 不构建 SDK；首次切换私有符号需要先通过手动 SDK 工作流更新产物，旧 schema 1 SDK 无法链接新 Go 库。完整性审计仍可读取旧清单，但原生测试明确拒绝没有私有符号的 SDK。

SDK 构建仅支持手动触发，与 RDP 等仓库保持一致。在 GitHub Actions 中选择 **Build video SDK pull request → Run workflow**，选择工作流分支；可用 `target_branch` 指定已有目标分支，留空时使用所选工作流分支。

手动启动后，三平台从同一源码提交构建，全部完成普通 C 链接、全归档链接、真实 cgo 链接及合成画面转换/缩放/编码/解码检查后，统一创建 SDK PR。发布过程不自动合并 PR、不覆盖目标分支，目标分支在构建期间推进时会停止发布。

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

调用者计算目标尺寸及单调递增的毫秒时间戳。BGRA 输入支持行填充，I420 输入允许三个平面使用独立步长；转换采用 BT.601 有限范围 I420，缩放采用双线性策略。编码输出宽高必须为偶数，最小 16×16，最高 1920×1080、30fps、8Mbps，Level 3.1 限制为 720p。独立帧和转换接口仍支持更小或奇数尺寸。编码器不会自行创建观看预设或网络预算。

输入为同步只读借用，调用返回前不得修改或释放；返回的 Annex-B 数据由 Go 持有，后续调用不覆盖。`Skipped` 表示编码器跳帧。转换函数写入调用方提供的缓冲，拒绝输入／输出重叠。编码器的方法内部串行化，关闭等待在途调用结束。

`UpdateRate` 失败会恢复旧配置；若恢复失败，返回 `h264.ErrUnusable`，实例只能关闭。尺寸／Level 变化由调用方创建候选实例并确认首个关键帧后再替换。错误支持 `errors.Is`，公共合同不包含 RDP 错误码。

关闭 cgo 或不支持的平台可以编译 Go API，能力返回不支持。支持平台必须提供私有 SDK 和本机编译器。正式依赖在首个 Go 库版本发布后固定到实际版本；本地通过相邻仓库 workspace，产品构建通过源码锁和临时 modfile 接入，不使用不存在的远程版本。

本次迁移的实测结果、体积变化及发布顺序见 [验证记录](docs/integration-validation.md)。
