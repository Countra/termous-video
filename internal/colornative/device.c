//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"
#include <stdio.h>
#include <stdlib.h>
#ifdef _WIN32
#include <dxgi1_6.h>
#endif
#ifdef __linux__
#include <dlfcn.h>
#endif

static int prepare_dispatch(tv_color *s) {
  if (!s->device)
    return 0;
  s->gpu = s->device->gpu;
#ifdef _WIN32
  IDXGIDevice *dxgi = NULL;
  IDXGIAdapter *adapter = NULL;
  DXGI_ADAPTER_DESC desc;
  if (SUCCEEDED(ID3D11Device_QueryInterface(s->device->device, &IID_IDXGIDevice, (void **)&dxgi))) {
    if (SUCCEEDED(IDXGIDevice_GetAdapter(dxgi, &adapter))) {
      if (SUCCEEDED(IDXGIAdapter_GetDesc(adapter, &desc)))
        WideCharToMultiByte(CP_UTF8, 0, desc.Description, -1, s->device_name, sizeof(s->device_name), NULL, NULL);
      IDXGIAdapter_Release(adapter);
    }
    IDXGIDevice_Release(dxgi);
  }
#else
  PFN_vkGetPhysicalDeviceProperties properties = (PFN_vkGetPhysicalDeviceProperties)
      s->device->get_proc_addr(s->device->instance, "vkGetPhysicalDeviceProperties");
  if (properties) {
    VkPhysicalDeviceProperties info;
    properties(s->device->phys_device, &info);
    snprintf(s->device_name, sizeof(s->device_name), "%s", info.deviceName);
  }
#endif
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
    tv_readback_destroy(s);
    pl_timer_destroy(s->gpu, &s->dispatch_timer);
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
  // 只在设备创建时按 DXGI 性能顺序选择硬件；失败后继续默认硬件与 WARP 路径。
  if (!software) {
    IDXGIFactory6 *factory = NULL;
    if (SUCCEEDED(CreateDXGIFactory1(&IID_IDXGIFactory6, (void **)&factory))) {
      for (UINT i = 0; i < 32; i++) {
        IDXGIAdapter1 *adapter = NULL;
        if (FAILED(IDXGIFactory6_EnumAdapterByGpuPreference(factory, i, DXGI_GPU_PREFERENCE_HIGH_PERFORMANCE,
                                                           &IID_IDXGIAdapter1, (void **)&adapter)))
          break;
        DXGI_ADAPTER_DESC1 desc;
        if (SUCCEEDED(IDXGIAdapter1_GetDesc1(adapter, &desc)) && !(desc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE)) {
          p.adapter = (IDXGIAdapter *)adapter;
          s->device = pl_d3d11_create(s->log, &p);
          if (prepare_dispatch(s)) {
            IDXGIAdapter1_Release(adapter);
            IDXGIFactory6_Release(factory);
            return s;
          }
          pl_d3d11_destroy(&s->device);
          s->gpu = NULL;
        }
        IDXGIAdapter1_Release(adapter);
      }
      IDXGIFactory6_Release(factory);
    }
    p.adapter = NULL;
  }
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
const char *tv_color_device(tv_color *s) { return s ? s->device_name : "unavailable"; }
