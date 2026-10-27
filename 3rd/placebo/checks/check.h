#pragma once
#include <libplacebo/gpu.h>
// Windows 也提供 Vulkan stub；验证 SDK 公开头文件及其依赖完整。
#include <libplacebo/vulkan.h>

// 返回 77 仅表示 Metal 没有可用设备；后端初始化或像素验证失败使用普通非零错误。
int placebo_check(int mode);
int placebo_render_check(pl_gpu gpu, pl_log log);
#ifdef __APPLE__
int placebo_metal_available(void);
#endif
