"""构建独立的渲染 SDK 组件；只有验证通过的静态产物进入暂存区。"""

import json
import shutil

from ..layout import BUILD_ROOT, TOOLS_ROOT, managed
from ..process import capture
from ..sdk_manifest import inventory
from .checks import verify_link
from .layout import archives, link_description
from .recipes import build_dependencies, meson_build
from .review import verify_review
from .sources import source_lock, verify_sources


def build_component(target, jobs, env, tools, destination, accepted):
    review = verify_review(target, env, accepted)
    tools = dict(tools)
    for key, name in (("meson", "meson"), ("pkgconfig", "pkg-config")):
        value = shutil.which(name, path=env.get("PATH"))
        if not value:
            raise RuntimeError(f"Required libplacebo build tool not found: {name}")
        tools[key] = value
    prefix = managed(f"prefix/placebo/{target}")
    # 前缀完全由本模块拥有；清空旧安装结果，避免把已禁用依赖混入新 SDK。
    if prefix.exists():
        shutil.rmtree(prefix)
    prefix.mkdir(parents=True)
    build_dependencies(target, prefix, tools, env, jobs)
    meson_build(target, prefix, tools, env, jobs)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "lib").mkdir()
    for name in archives(target):
        shutil.copyfile(prefix / "lib" / name, destination / "lib" / name)
    shutil.copytree(prefix / "include/libplacebo", destination / "include/libplacebo")
    if target != "windows/amd64":
        for name in ("vulkan", "vk_video"):
            shutil.copytree(managed(f"sources/vulkan-headers/include/{name}"), destination / "include" / name)
    shutil.copyfile(TOOLS_ROOT / "placebo-lock.json", destination / "source-lock.json")
    (destination / "link.json").write_text(json.dumps(link_description(target), indent=2) + "\n", encoding="utf-8")
    verification = verify_link(destination, target, tools, env)
    verify_sources(target, env)
    data = {"schema": 1, "scope": "libplacebo_static", "platform": target, "symbol_renaming": False,
            "sources": source_lock(), "review_sha256": review, "verification": verification,
            "toolchain": {key: capture([tools[key], "--version"], BUILD_ROOT, env).splitlines()[0]
                          for key in ("meson", "pkgconfig")}, "files": inventory(destination)}
    (destination / "manifest.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    from .manifest import verify_component
    verify_component(destination, target)
    return data
