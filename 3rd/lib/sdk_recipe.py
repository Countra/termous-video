"""只追踪 SDK 生产输入，并识别已核验的旧版配方摘要。"""

import hashlib
import json
import re
import stat
from pathlib import PurePosixPath

ALGORITHM = "termous-video-sdk-inputs-v2"
ROOT_FILES = {"build.py", "placebo.py", "build-lock.json", "placebo-lock.json", "CMakeLists.txt",
              "placebo/upstream-review.json"}
INPUT_TREES = ("cmake", "lib", "placebo/moltenvk")
# 这些模块只验证产物或维护清单，不生成交付的库、头文件和链接配置。
VALIDATION_FILES = {"lib/sdk_recipe.py", "lib/sdk_manifest.py", "lib/sdk_link.py",
                    "lib/sdk_install.py", "lib/placebo/checks.py", "lib/placebo/manifest.py"}


def is_build_input(relative):
    path = PurePosixPath(relative)
    if ("__pycache__" in path.parts or path.suffix in {".md", ".pyc", ".pyo"}
            or relative in VALIDATION_FILES):
        return False
    return relative in ROOT_FILES or any(relative.startswith(tree + "/") for tree in INPUT_TREES)


def _input_files(tools_root):
    pending = [tools_root]
    while pending:
        path = pending.pop()
        relative = path.relative_to(tools_root).as_posix()
        included = is_build_input(relative)
        parent = relative == "." or relative in INPUT_TREES or any(
            name.startswith(relative + "/") for name in (*ROOT_FILES, *INPUT_TREES))
        if not included and not parent:
            continue
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"Links are not allowed in SDK build inputs: {relative}")
        if stat.S_ISDIR(info.st_mode):
            # 先检查当前目录，再枚举下一层，不能通过 rglob 提前遍历链接或重解析点。
            pending.extend(path.iterdir())
        elif not stat.S_ISREG(info.st_mode):
            raise ValueError(f"Special files are not allowed in SDK build inputs: {relative}")
        elif included:
            yield path
        else:
            raise ValueError(f"SDK build input parent must be a directory: {relative}")


def recipe_hash(tools_root):
    # 算法版本进入摘要；固定 POSIX 路径顺序和 LF，避免平台与 Git 换行设置造成差异。
    digest = hashlib.sha256(ALGORITHM.encode() + b"\0")
    for path in sorted(_input_files(tools_root), key=lambda item: item.relative_to(tools_root).as_posix()):
        relative = path.relative_to(tools_root).as_posix()
        digest.update(("3rd/" + relative).encode() + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def matches_recipe(tools_root, manifest, current):
    if manifest.get("recipe_sha256") == current:
        return True
    # 兼容表来自已核验的历史源码，不读取 Git 历史、不联网，也不改写 SDK 清单。
    path = tools_root / "sdk-recipe-compat.json"
    try:
        compatibility = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot read SDK recipe compatibility metadata: {path}") from error
    if (not isinstance(compatibility, dict) or type(compatibility.get("schema")) is not int
            or compatibility["schema"] != 1
            or compatibility.get("algorithm") != ALGORITHM or not isinstance(compatibility.get("legacy"), list)):
        raise ValueError("Invalid SDK recipe compatibility metadata")
    seen = set()
    matched = False
    for entry in compatibility["legacy"]:
        if (not isinstance(entry, dict) or set(entry) != {"source_commit", "recipe_sha256", "inputs_sha256"}
                or any(not isinstance(entry[key], str) or not re.fullmatch(pattern, entry[key])
                       for key, pattern in (("source_commit", r"[0-9a-f]{40}"),
                                            ("recipe_sha256", r"[0-9a-f]{64}"),
                                            ("inputs_sha256", r"[0-9a-f]{64}")))):
            raise ValueError("Invalid legacy SDK recipe record")
        identity = (entry["source_commit"], entry["recipe_sha256"])
        if identity in seen:
            raise ValueError("Duplicate legacy SDK recipe record")
        seen.add(identity)
        matched |= (manifest.get("source_dirty") is False
                    and identity == (manifest.get("source_commit"), manifest.get("recipe_sha256"))
                    and entry["inputs_sha256"] == current)
    return matched
