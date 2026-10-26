# termous-video

Termous 公共视频处理库的依赖基础。当前阶段提供 OpenH264 与 libyuv 的固定版本构建、静态 SDK、C/cgo 验证和 CI 发布流程；尚未提供生产 Go API，也未迁移 RDP 编码实现。

仓库：<https://github.com/Countra/termous-video>

| 目标 | 工具链 | SDK 目录 |
|---|---|---|
| Windows amd64 | MinGW-w64 GCC，MINGW64/MSVCRT | `sdk/windows/amd64` |
| Linux amd64 | GCC | `sdk/linux/amd64` |
| macOS arm64 | Apple Clang，macOS 12+ | `sdk/darwin/arm64` |

每套 SDK 包含独立的 `libopenh264.a`、`libyuv.a`、头文件、许可证、依赖锁和完整文件校验清单。第三方库不合并；不分发 DLL、可执行程序或独立视频进程。OpenH264 静态库保留上游编解码能力，但这不表示已经增加业务解码接口。

## 目录

- `3rd/`：全平台 Python 入口、本仓库 CMake 配方、验证程序和测试。
- `build/`：下载的 Git 仓库、编译输出、日志、临时 SDK 和合成画面验证程序，忽略版本控制。
- `sdk/<系统>/<架构>/`：验证通过的安装产物，由 CI 通过 PR 更新。

## 使用

```text
python 3rd/check.py
python -B -m unittest discover -s 3rd/tests -v
python 3rd/build.py prepare
python 3rd/build.py build --jobs 8
```

详细工具链要求、缓存配置和链接说明见 [3rd/README.md](3rd/README.md)。只支持本机构建，不在 Windows 上交叉编译其他平台。

## CI

每次 push / PR 在三个平台执行离线工具测试，并校验仓库中已有 SDK 的文件完整性。该检查允许 SDK 暂时落后于待重建的源码配方；正式构建和发布仍要求当前配方与固定依赖完全匹配。`main` 上的 `3rd`、构建工作流或换行规则变更会自动构建三平台 SDK；也可手动运行 **Build video SDK pull request** 指定已有目标分支。

三平台从同一源码提交构建，全部完成普通 C 链接、全归档链接、真实 cgo 链接及合成画面转换/缩放/编码/解码检查后，统一创建 SDK PR。只修改 `sdk` 的 PR 合并不会再次触发 SDK 构建。发布过程不自动合并 PR、不覆盖目标分支，目标分支在构建期间推进时会停止发布。

GitHub 仓库需允许 Actions 创建 Pull Request（Settings → Actions → General），发布 job 使用仓库自带 `GITHUB_TOKEN`。其他 job 只有读取权限。

所有运行验证只使用内存中生成的图案，不读取桌面、摄像头或真实用户文件。当前库不包含网络传输、采集、权限或会话业务。
