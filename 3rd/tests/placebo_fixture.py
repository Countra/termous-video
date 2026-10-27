"""离线 SDK 清单夹具，不执行上游代码或创建图形设备。"""

import json

from lib.placebo.layout import archives, link_description
from lib.placebo.review import review_digest
from lib.placebo.sources import source_lock
from lib.sdk_manifest import inventory


def fixture(directory, target):
    files = {"lib/" + name: b"!<arch>\n" for name in archives(target)}
    for name in ("config.h", "renderer.h", "colorspace.h", "gpu.h"):
        files["include/libplacebo/" + name] = b"header"
    if target != "windows/amd64":
        files["include/vulkan/vulkan.h"] = b"vulkan"
    files.update({"source-lock.json": json.dumps(source_lock()).encode(),
                  "link.json": json.dumps(link_description(target)).encode()})
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    data = {"schema": 1, "scope": "libplacebo_static", "platform": target, "symbol_renaming": False,
            "sources": source_lock(), "review_sha256": review_digest(),
            "verification": {"c_link": True, "whole_archive_link": True, "cgo_link": True,
                             "api_smoke": True, "hdr_render": "passed", "desktop_captured": False},
            "files": inventory(directory)}
    (directory / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
