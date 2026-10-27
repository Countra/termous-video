"""SDK 来源和完整载荷校验，发布阶段不信任下载产物的路径或声明。"""

import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path

from .layout import PROJECT_ROOT, TOOLS_ROOT
from .platforms import TARGETS
from .sources import source_lock, validate_source_lock
from .symbols import ARCHIVES, HEADER, PREFIX


def checked_files(directory):
    directory = Path(directory).absolute()
    for path in (directory, *directory.parents):
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0)
                                 & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Links and reparse points are not allowed: {path}")
    if not directory.is_dir():
        raise ValueError(f"Directory does not exist: {directory}")
    result = []
    for path in sorted(directory.rglob("*")):
        info = path.lstat()
        if (stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError(f"Links are not allowed in the SDK: {path}")
        if stat.S_ISREG(info.st_mode):
            if info.st_size >= 100 * 1024 * 1024:
                raise ValueError(f"File exceeds the regular Git size limit: {path}")
            result.append(path)
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Special files are not allowed in the SDK: {path}")
    return result


def inventory(directory):
    directory = Path(directory).absolute()
    return {p.relative_to(directory).as_posix(): {"sha256": sha256(p), "bytes": p.stat().st_size}
            for p in checked_files(directory) if p != directory / "manifest.json"}


def recipe_hash():
    digest = hashlib.sha256()
    # WindowsPath 默认按大小写不敏感排序，必须用统一的 POSIX 相对名生成跨平台摘要。
    for path in sorted(TOOLS_ROOT.rglob("*"), key=lambda item: item.relative_to(PROJECT_ROOT).as_posix()):
        if path.is_file() and (path.suffix in (".py", ".cmake", ".json", ".in", ".c", ".cc", ".m", ".mm", ".h", ".go", ".md")
                               or path.name == "CMakeLists.txt"):
            digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode() + b"\0")
            digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def source_record(status_log=None):
    result = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=PROJECT_ROOT,
                            capture_output=True, text=True, check=False)
    commit = result.stdout.strip() if result.returncode == 0 else None
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--", ".", ":(exclude)sdk"],
        cwd=PROJECT_ROOT, text=True, encoding="utf-8").rstrip("\r\n")
    if status_log is not None:
        status_log.parent.mkdir(parents=True, exist_ok=True)
        status_log.write_text(f"Source commit: {commit or '(unavailable)'}\n"
                              f"Working tree changes (excluding SDK):\n{dirty}\n", encoding="utf-8")
    return {"source_commit": commit, "source_dirty": bool(dirty)}


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_manifest(directory, target, source_commit=None, *, current_recipe=True):
    directory = Path(directory).absolute()
    payload = inventory(directory)
    data = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or target not in TARGETS or data.get("schema") not in (1, 2) or data.get("platform") != target
            or data.get("scope") != "video_dependencies" or data.get("library_type") != "static"
            or data.get("build_type") != "Release"):
        raise ValueError("SDK target, scope or build format mismatch")
    recipe = data.get("recipe_sha256")
    if (data.get("files") != payload or not isinstance(recipe, str)
            or not re.fullmatch(r"[0-9a-f]{64}", recipe)):
        raise ValueError("SDK file digest or recipe mismatch")
    lock = json.loads((directory / "build-lock.json").read_text(encoding="utf-8"))
    validate_source_lock(lock)
    if data.get("sources") != lock:
        raise ValueError("SDK dependency lock mismatch")
    # 常规 CI 校验已有 SDK 的完整性，允许它暂时落后于尚未重建的源码配方。
    # 构建、安装和发布仍必须与当前配方及依赖锁完全一致。
    if current_recipe and (recipe != recipe_hash() or lock != source_lock()):
        raise ValueError("SDK source lock or recipe mismatch; rebuild the SDK")
    recorded_commit = data.get("source_commit")
    if (not isinstance(data.get("source_dirty"), bool)
            or (recorded_commit is None and data["source_dirty"] is not True)
            or (recorded_commit is not None and
                (not isinstance(recorded_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", recorded_commit)))):
        raise ValueError("Invalid SDK source provenance")
    if source_commit is not None and (
            not re.fullmatch(r"[0-9a-f]{40}", source_commit)
            or data.get("source_commit") != source_commit or data.get("source_dirty") is not False):
        raise ValueError("SDK was not built from the selected clean commit")
    isolated = data["schema"] == 2
    libraries = tuple(ARCHIVES.values()) if isolated else tuple(ARCHIVES)
    if current_recipe and not isolated:
        raise ValueError("SDK has no private symbols; run the manual SDK workflow")
    if isolated:
        isolation = data.get("isolation", {})
        if (not isinstance(isolation, dict) or isolation.get("version") != 1
                or isolation.get("prefix") != PREFIX or type(isolation.get("symbols")) is not int
                or isolation["symbols"] < 1):
            raise ValueError("SDK symbol isolation metadata is invalid")
    required = {"include/wels/codec_api.h",
                "include/wels/codec_app_def.h", "include/wels/codec_def.h", "include/wels/codec_ver.h",
                "include/libyuv.h", "include/libyuv/convert.h", "README.md", "build-lock.json",
                "licenses/OpenH264-LICENSE", "licenses/libyuv-LICENSE", "licenses/libyuv-PATENTS"}
    required.update("lib/" + name for name in libraries)
    if isolated:
        required.update(("include/" + HEADER, "symbols/rename.map"))
    components = data.get("components", {})
    if components not in ({}, {"placebo": "placebo/manifest.json"}):
        raise ValueError("Unexpected SDK components")
    if current_recipe and "placebo" not in components:
        raise ValueError("SDK is missing the libplacebo component; run the manual SDK workflow")
    if "placebo" in components:
        from .placebo.manifest import verify_component
        verify_component(directory / "placebo", target, current_recipe=current_recipe)
    if not required <= payload.keys():
        raise ValueError("SDK is missing required libraries, headers or licenses")
    for name in payload:
        if "placebo" in components and name.startswith("placebo/"):
            continue
        if not (name.startswith(("include/", "lib/", "licenses/")) or name in ("README.md", "build-lock.json", "symbols/rename.map")):
            raise ValueError(f"Unexpected SDK file: {name}")
        if name.startswith("lib/") and name not in {"lib/" + library for library in libraries}:
            raise ValueError(f"Unexpected SDK library: {name}")
        if re.search(r"\.(dll|exe|so|dylib)(\.|$)", name, re.IGNORECASE):
            raise ValueError(f"Dynamic libraries and executables are not allowed: {name}")
    for name in libraries:
        with (directory / "lib" / name).open("rb") as stream:
            if stream.read(8) != b"!<arch>\n":
                raise ValueError(f"Not a self-contained static archive: {name}")
    checks = data.get("verification", {})
    if not isinstance(checks, dict) or any(
            checks.get(key) is not True for key in ("c_link", "whole_archive_link", "cgo_link", "synthetic_smoke")):
        raise ValueError("SDK is missing required link and runtime verification")
    if checks.get("desktop_captured") is not False:
        raise ValueError("SDK verification must not capture the desktop")
    if "placebo" in components and checks.get("placebo_coexistence") is not True:
        raise ValueError("SDK is missing libplacebo and codec coexistence verification")
    return data
