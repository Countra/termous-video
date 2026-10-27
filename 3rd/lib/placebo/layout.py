"""公开 SDK 文件清单与链接顺序；不改写渲染依赖的符号。"""

from ..platforms import link_flags


def archives(target):
    result = ["libplacebo.a"]
    if target == "darwin/arm64":
        result += ["libMoltenVK.a", "libMoltenVK_ShaderConverter.a", "libMoltenVK_Common.a",
                   "libspirv-cross-msl.a", "libspirv-cross-reflect.a", "libspirv-cross-glsl.a", "libspirv-cross-core.a"]
    elif target == "windows/amd64":
        result += ["libspirv-cross-c.a", "libspirv-cross-hlsl.a", "libspirv-cross-glsl.a",
                   "libspirv-cross-core.a"]
    elif target != "linux/amd64":
        raise ValueError(f"Unsupported libplacebo target: {target}")
    result += ["libSPIRV.a", "libglslang.a", "libglslang-default-resource-limits.a"]
    if target == "windows/amd64":
        result.append("libplacebo_ucrt_math.a")
    return result


def system_flags(target):
    flags = link_flags(target)
    if target == "windows/amd64":
        return [*flags, "-lversion", "-lshlwapi", "-lole32", "-luuid"]
    if target == "linux/amd64":
        return [*flags, "-ldl"]
    frameworks = ("Foundation", "Metal", "AppKit", "IOKit", "IOSurface", "QuartzCore", "CoreGraphics")
    return [*flags, "-lobjc", "-Wl,-ObjC", *(arg for name in frameworks for arg in ("-framework", name))]


def link_description(target):
    return {"archives": ["lib/" + name for name in archives(target)],
            "compile_flags": ["-DPL_STATIC", "-std=c11"], "system_flags": system_flags(target),
            "backend": "d3d11" if target.startswith("windows/") else "vulkan",
            "vulkan_loader": "static_moltenvk" if target.startswith("darwin/") else
                             "system_dlopen" if target.startswith("linux/") else None,
            "symbol_renaming": False}
