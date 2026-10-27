"""单独锁定渲染依赖，保留现有编解码 SDK 的来源合同。"""

import json
import re

from ..layout import TOOLS_ROOT
from ..platforms import TARGETS
from ..sources import prepare_sources, verify_source

URLS = {
    "libplacebo": "https://code.videolan.org/videolan/libplacebo.git",
    "glslang": "https://github.com/KhronosGroup/glslang.git",
    "spirv-cross": "https://github.com/KhronosGroup/SPIRV-Cross.git",
    "vulkan-headers": "https://github.com/KhronosGroup/Vulkan-Headers.git",
    "moltenvk": "https://github.com/KhronosGroup/MoltenVK.git",
    "cereal": "https://github.com/USCiLab/cereal.git",
    "fast-float": "https://github.com/fastfloat/fast_float.git",
    "jinja": "https://github.com/pallets/jinja.git",
    "markupsafe": "https://github.com/pallets/markupsafe.git",
}


def validate_lock(data):
    if not isinstance(data, dict) or data.get("schema") != 1 or set(data) != {"schema", *URLS}:
        raise ValueError("Invalid libplacebo dependency lock")
    for name, url in URLS.items():
        item = data[name]
        if (not isinstance(item, dict) or set(item) != {"url", "version", "revision"}
                or item["url"] != url or not isinstance(item["revision"], str)
                or not re.fullmatch(r"[0-9a-f]{40}", item["revision"])
                or not isinstance(item["version"], str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", item["version"])):
            raise ValueError(f"Invalid libplacebo pinned source: {name}")


def source_lock():
    data = json.loads((TOOLS_ROOT / "placebo-lock.json").read_text(encoding="utf-8"))
    validate_lock(data)
    return data


def dependencies(target):
    if target not in TARGETS:
        raise ValueError(f"Unsupported libplacebo target: {target}")
    # D3D11 构建仍编译 Vulkan stub，公开头文件也依赖 Vulkan-Headers。
    common = ["libplacebo", "glslang", "fast-float", "jinja", "markupsafe", "vulkan-headers"]
    if target == "windows/amd64":
        return [*common, "spirv-cross"]
    if target == "linux/amd64":
        return common
    return [*common, "spirv-cross", "moltenvk", "cereal"]


def prepare(target, env):
    lock = source_lock()
    prepare_sources({name: lock[name] for name in dependencies(target)}, env)
    print(f"Pinned libplacebo sources prepared: {target}; no upstream scripts were executed.")


def verify_sources(target, env):
    lock = source_lock()
    for name in dependencies(target):
        verify_source(name, lock[name], env)
