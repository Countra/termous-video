//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"
#include <stdio.h>
#include <stdlib.h>
#ifdef __linux__
#include <dlfcn.h>
#endif

static int prepare_dispatch(tv_color *s) {
  if (!s->device)
    return 0;
  s->gpu = s->device->gpu;
  if (!pl_find_fmt(s->gpu, PL_FMT_FLOAT, 4, 16, 16, PL_FMT_CAP_SAMPLEABLE) ||
      !pl_find_fmt(s->gpu, PL_FMT_UNORM, 4, 16, 16, PL_FMT_CAP_LINEAR) ||
      !pl_find_fmt(s->gpu, PL_FMT_UNORM, 4, 8, 8,
                   PL_FMT_CAP_RENDERABLE | PL_FMT_CAP_HOST_READABLE))
    return 0;
  pl_matrix3x3 matrix = pl_get_color_mapping_matrix(
      pl_raw_primaries_get(PL_COLOR_PRIM_BT_709),
      pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020), PL_INTENT_RELATIVE_COLORIMETRIC);
  // libplacebo 的矩阵按行存储；GLSL uniform 使用列优先布局。
  for (int row = 0; row < 3; row++)
    for (int col = 0; col < 3; col++)
      s->to_work[col * 3 + row] = matrix.m[row][col];
  s->dispatch = pl_dispatch_create(s->log, s->gpu);
  return s->dispatch != NULL;
}

void tv_color_destroy(tv_color *s) {
  if (!s)
    return;
  if (s->gpu) {
    pl_shader_obj_destroy(&s->color_map);
    pl_dispatch_destroy(&s->dispatch);
    pl_tex_destroy(s->gpu, &s->input);
    pl_tex_destroy(s->gpu, &s->output);
  }
#ifdef _WIN32
  pl_d3d11_destroy(&s->device);
#else
  pl_vulkan_destroy(&s->device);
#ifdef __linux__
  if (s->loader)
    dlclose(s->loader);
#endif
#endif
  pl_log_destroy(&s->log);
  free(s);
}
tv_color *tv_color_create(int software) {
  tv_color *s = calloc(1, sizeof(*s));
  if (!s)
    return NULL;
  s->log = pl_log_create(PL_API_VER, pl_log_params(.log_cb = pl_log_simple,
                                                   .log_priv = stderr,
                                                   .log_level = PL_LOG_ERR));
#ifdef _WIN32
  struct pl_d3d11_params p = pl_d3d11_default_params;
  p.allow_software = software != 0;
  p.force_software = software != 0;
  s->device = pl_d3d11_create(s->log, &p);
  if (prepare_dispatch(s))
    return s;
  // 设备和必要纹理格式都可用才算初始化成功；回落仅使用系统 WARP。
  pl_d3d11_destroy(&s->device);
  s->gpu = NULL;
  if (!software) {
    p.force_software = true;
    p.allow_software = true;
    s->device = pl_d3d11_create(s->log, &p);
    if (prepare_dispatch(s))
      return s;
  }
#else
  struct pl_vulkan_params p = pl_vulkan_default_params;
  // 强制软件模式只用于 Windows WARP 验证；Vulkan 自动选择系统已有设备。
  if (software) {
    tv_color_destroy(s);
    return NULL;
  }
  p.allow_software = true;
#ifdef __APPLE__
  p.get_proc_addr = vkGetInstanceProcAddr;
#else
  // 软件设备的选择交给系统 Vulkan；不下载或捆绑驱动。
  s->loader = dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL);
  if (s->loader)
    p.get_proc_addr =
        (PFN_vkGetInstanceProcAddr)dlsym(s->loader, "vkGetInstanceProcAddr");
#endif
  if (p.get_proc_addr)
    s->device = pl_vulkan_create(s->log, &p);
  if (prepare_dispatch(s))
    return s;
#endif
  tv_color_destroy(s);
  return NULL;
}
const char *tv_color_backend(tv_color *s) {
  if (!s)
    return "unavailable";
#ifdef _WIN32
  return s->device->software ? "d3d11-warp" : "d3d11";
#elif defined(__APPLE__)
  return "metal-moltenvk";
#else
  return "vulkan";
#endif
}
int tv_color_failed(tv_color *s) { return !s || pl_gpu_is_failed(s->gpu); }
