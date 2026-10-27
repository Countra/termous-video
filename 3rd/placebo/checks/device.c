#include "check.h"
#include <stdio.h>
#include <libplacebo/colorspace.h>
#include <libplacebo/log.h>

#ifdef _WIN32
#include <libplacebo/d3d11.h>

static int check_system_graphics_runtime(void)
{
    const wchar_t *names[] = {L"d3d11.dll", L"dxgi.dll", L"d3dcompiler_47.dll"};
    wchar_t system[MAX_PATH];
    UINT length = GetSystemDirectoryW(system, MAX_PATH);
    if (!length || length >= MAX_PATH)
        return 4;
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i) {
        wchar_t path[MAX_PATH];
        HMODULE module = GetModuleHandleW(names[i]);
        DWORD count = module ? GetModuleFileNameW(module, path, MAX_PATH) : 0;
        if (count <= length || count >= MAX_PATH || path[length] != L'\\' ||
            CompareStringOrdinal(system, length, path, length, TRUE) != CSTR_EQUAL)
            return 4;
    }
    puts("D3D11, DXGI and D3DCompiler 47 loaded from the Windows system directory");
    return 0;
}
#else
#include <libplacebo/vulkan.h>
#ifdef __linux__
#include <dlfcn.h>
#endif
#endif

int placebo_check(int mode)
{
    if (PL_API_VER != 387 || PL_COLOR_SCRGB_WHITE != 80.0f ||
        pl_color_space_srgb.primaries != PL_COLOR_PRIM_BT_709)
        return 1;
    if (mode == 0) {
        puts("libplacebo static C API verified");
        return 0;
    }
#ifdef __APPLE__
    if (!placebo_metal_available()) {
        fputs("Metal device unavailable; rendering was not verified\n", stderr);
        return 77;
    }
#endif
    pl_log log = pl_log_create(PL_API_VER, pl_log_params(
        .log_cb = pl_log_simple, .log_level = PL_LOG_INFO));
    int result = 5;
#ifdef _WIN32
    struct pl_d3d11_params params = pl_d3d11_default_params;
    params.force_software = mode == 2;
    params.allow_software = mode != 3;
    pl_d3d11 device = pl_d3d11_create(log, &params);
    if (device) {
        printf("D3D11 backend: %s\n", device->software ? "WARP" : "hardware");
        result = placebo_render_check(device->gpu, log);
        if (result == 0)
            result = check_system_graphics_runtime();
        pl_d3d11_destroy(&device);
    }
#else
    struct pl_vulkan_params params = pl_vulkan_default_params;
    params.allow_software = true;
#ifdef __APPLE__
    // 直接调用静态 MoltenVK，运行时不查找 libvulkan 或 MoltenVK dylib。
    params.get_proc_addr = vkGetInstanceProcAddr;
#else
    void *loader = dlopen("libvulkan.so.1", RTLD_NOW | RTLD_LOCAL);
    if (loader)
        params.get_proc_addr = (PFN_vkGetInstanceProcAddr)dlsym(loader, "vkGetInstanceProcAddr");
#endif
    pl_vulkan device = params.get_proc_addr ? pl_vulkan_create(log, &params) : NULL;
    if (device) {
        result = placebo_render_check(device->gpu, log);
        pl_vulkan_destroy(&device);
    }
#ifdef __linux__
    if (loader)
        dlclose(loader);
#endif
#endif
    pl_log_destroy(&log);
    if (result == 5)
        fputs("GPU backend initialization failed\n", stderr);
    return result;
}
