"""验证可分发的渲染 SDK；消费方无需 Meson、LLVM 或上游源码。"""

import json
import re

from ..sdk_manifest import inventory
from .layout import archives, link_description
from .review import review_digest
from .sources import source_lock, validate_lock


def verify_component(directory, target, *, current_recipe=True):
    payload = inventory(directory)
    data = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or data.get("schema") != 1 or data.get("platform") != target
            or data.get("scope") != "libplacebo_static" or data.get("symbol_renaming") is not False
            or data.get("files") != payload):
        raise ValueError("libplacebo SDK target, format or file digest mismatch")
    lock = json.loads((directory / "source-lock.json").read_text(encoding="utf-8"))
    validate_lock(lock)
    review = data.get("review_sha256")
    if (data.get("sources") != lock or not isinstance(review, str)
            or not re.fullmatch(r"[0-9a-f]{64}", review)):
        raise ValueError("Invalid libplacebo SDK source or review record")
    if current_recipe and (lock != source_lock() or review != review_digest()):
        raise ValueError("libplacebo SDK source or review changed; rebuild the SDK")
    if json.loads((directory / "link.json").read_text(encoding="utf-8")) != link_description(target):
        raise ValueError("libplacebo SDK link description mismatch")
    libraries = {"lib/" + name for name in archives(target)}
    required = libraries | {"include/libplacebo/config.h", "include/libplacebo/renderer.h",
                            "include/libplacebo/colorspace.h", "include/libplacebo/gpu.h",
                            "include/libplacebo/vulkan.h", "include/vulkan/vulkan.h",
                            "include/vulkan/vulkan_core.h", "include/vulkan/vk_platform.h",
                            "include/vk_video/vulkan_video_codecs_common.h",
                            "source-lock.json", "link.json"}
    if not required <= payload.keys():
        raise ValueError("libplacebo SDK is missing required files")
    for name in payload:
        if (name not in required and not name.startswith("include/")
                or re.search(r"\.(dll|exe|so|dylib)(\.|$)", name, re.IGNORECASE)):
            raise ValueError(f"Unexpected libplacebo SDK file: {name}")
    for name in libraries:
        with (directory / name).open("rb") as stream:
            if stream.read(8) != b"!<arch>\n":
                raise ValueError(f"libplacebo SDK requires regular static archives: {name}")
    checks = data.get("verification", {})
    if (not isinstance(checks, dict) or any(checks.get(key) is not True
            for key in ("c_link", "whole_archive_link", "cgo_link", "api_smoke"))
            or checks.get("desktop_captured") is not False):
        raise ValueError("libplacebo SDK is missing required link verification")
    allowed = {"passed", "unavailable"} if target == "darwin/arm64" else {"passed"}
    if checks.get("hdr_render") not in allowed:
        raise ValueError("libplacebo SDK has no valid HDR rendering result")
    return data
