# 公共编码库迁移验证

日期：2026-10-26。此次在 Windows amd64 使用 Go 1.27.1、MinGW-w64 GCC 16.2.0 验证。测试仅使用合成画面，没有采集桌面或连接真实 RDP/VNC。未提交、推送或触发 GitHub 工作流。

## 已执行结果

- 公共 Go API 的转换、缩放、编码、参数更新、关闭、并发及关闭 cgo 的降级测试通过。
- 验证了带行填充和奇数源尺寸、目标缓冲复用、BT.601 有限范围颜色、Annex-B 输出所有权、SPS/PPS/IDR、Baseline/Level、实际解码尺寸和亮度。
- 复查发现 OpenH264 预处理共用 U 步长读取 U/V 平面；不同步长的 I420 输入曾将末行预期 V=240 解码为 10。已仅对该情况整理原生缓冲，U/V 两种大小关系及相同步长填充均通过实际解码检查，常规 BGRA 路径不增加复制。
- 编码输出最小尺寸已按 OpenH264 的真实约束修正为 16×16，并通过实际解码验证；创建时拒绝过小或奇数输出，帧与独立转换接口仍允许更小及奇数尺寸。
- 原生故障夹具覆盖参数部分更新失败后的恢复，以及恢复失败后实例不可用。RDP 测试确认公共库已回滚时不重复更新；不可恢复时不继续编码或发送成功回执。
- RDP 原生全量 Go 测试、公共库 race、RDP 视频服务 race、Core 的 RDP 适配器与 worker 管理测试通过。
- video 工具测试 41 项，40 项通过、1 项因本机符号链接权限跳过。buildtools 全量 242 项通过、8 项跳过，Ruff 通过。
- RDP 工具测试 41 项，39 项通过、1 项跳过，1 项因当前 SDK 配方摘要尚未更新失败；保留严格校验，等待手动 SDK 工作流生成新的清单。
- 两套 OpenH264/libyuv 使用两种归档顺序共同链接，分别转换、缩放、编码和解码成功；入口地址检查确认绑定独立。
- 公共库测试程序仅依赖 KERNEL32.dll、msvcrt.dll；最终 worker 仅依赖原有 Windows 系统 DLL。搬迁 worker、限制 PATH 后，启动、原生及视频能力、关闭均通过。
- 实际调用 buildtools 的临时 modfile 装配后，video、RDP 和 Core 在关闭 workspace、禁止联网且启用 `-mod=readonly` 时均能解析完整包依赖。此检查发现并修复了 Core 的 `x/image` 校验和及其传递最低版本未完整记录的问题；版本与此前 workspace 实际选择一致，未引入新的版本选择策略。
- 复查修复后重新通过公共库原生/race/关闭 cgo 测试、RDP 全量原生测试，以及 Core 的 RDP、worker 管理、截图、图片缓存、桌面工作流模型和远控服务回归；最终 worker 已重新链接并完成搬迁运行检查。

Windows 测试使用 `build/checks/private-sdk/windows/amd64` 中的本地验证 SDK，未替换已提交的 SDK。它不是发布产物；普通原生 CI 仍需要正式 schema 2 SDK。

## 性能与体积

同机 Ryzen 9 7900X，合成输入、每项 15 次、两轮短程基准：

| 场景 | 迁移前 | 公共库 | Go 分配次数 |
|---|---|---|---|
| 1080p 编码 | 10.43 / 10.51 ms | 10.64 / 11.13 ms | 3 → 2 |
| 4K 缩小到 1080p 并编码 | 13.09 / 13.27 ms | 13.20 / 14.35 ms | 3 → 2 |

该短程结果不能证明性能提升，也不代表真实交互或原生内存峰值。持续负载、资源占用和其他平台性能仍需对应环境验证。

worker 以 RDP 提交 `abef7cae36cfd88cac593f2d36c3c8bea21fb975` 为迁移前基线，使用相同 Go、GCC、`-trimpath -buildvcs=false -ldflags="-s -w"` 比较：21,779,968 → 22,633,984 字节，增加 854,016 字节（约 3.9%，包含本次复查修复）。产物位于工作区 `TEMP/video-validation`。

验证曾发现 LLVM 改写 COFF 后给 BSS 留下非零文件偏移，导致 worker 额外落盘约 32 MiB 的未初始化数据。现已在 SDK 隔离阶段修复该字段，并在原生验证、Go 链接及最终 worker 检查中拒绝此类产物。

## 发布顺序与未完成验收

1. 提交 video 的隔离配方及公共库，手动运行 **Build video SDK pull request**；三平台构建和合成运行通过后合入 SDK PR。
2. RDP 的 `VIDEO_REF` 指向包含公共库与正式私有 SDK 的版本，再手动运行 **Build native SDK pull request**，更新三个保留平台的 SDK 配方清单。
3. 验证普通 push/PR CI、最终产品构建；video 首个可用模块版本发布后，再将 Core/RDP 固定到真实远程版本。发布前继续使用 workspace 或 buildtools 的源码锁与临时 modfile。

Linux amd64、macOS arm64 本次完成静态检查和 CI 接入，尚未执行此次迁移的真实链接、运行及性能验收。三平台支持最终以对应平台 CI 的结果为准。
