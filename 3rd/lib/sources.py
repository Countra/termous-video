"""只准备固定提交源码；构建不执行上游 Make、CMake 或脚本。"""

import json
import re
import shutil
import subprocess

from .layout import TOOLS_ROOT, managed
from .process import capture, run

URLS = {"x264": "https://code.videolan.org/videolan/x264.git",
        "libyuv": "https://chromium.googlesource.com/libyuv/libyuv"}


def source_lock():
    data = json.loads((TOOLS_ROOT / "build-lock.json").read_text(encoding="utf-8"))
    validate_source_lock(data)
    return data


def validate_source_lock(data):
    if not isinstance(data, dict) or data.get("schema") != 2 or set(data) != {"schema", *URLS}:
        raise ValueError("Invalid dependency lock schema")
    for name, url in URLS.items():
        item = data[name]
        if (not isinstance(item, dict) or item.get("url") != url
                or not isinstance(item.get("revision"), str)
                or not re.fullmatch(r"[0-9a-f]{40}", item["revision"])
                or not isinstance(item.get("version"), str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}", item["version"])):
            raise ValueError(f"Invalid pinned source: {name}")


def git_command(env):
    git = shutil.which("git", path=env.get("PATH"))
    if not git:
        raise RuntimeError("Git was not found")
    hooks = managed("cache/empty-hooks")
    hooks.mkdir(parents=True, exist_ok=True)
    return [git, "-c", f"core.hooksPath={hooks}", "-c", "core.autocrlf=false",
            "-c", "core.eol=lf", "-c", "core.longpaths=true"]


def verify_source(name, item, env):
    path = managed(f"sources/{name}")
    git = git_command(env)
    if capture([*git, "remote", "get-url", "origin"], path, env) != item["url"]:
        raise ValueError(f"Source remote mismatch: {name}")
    if capture([*git, "rev-parse", "HEAD"], path, env) != item["revision"]:
        raise ValueError(f"Source revision mismatch: {name}; run prepare first")
    # 包含忽略文件，防止额外头文件覆盖固定提交中的文件。
    if capture([*git, "status", "--porcelain", "--untracked-files=all", "--ignored"], path, env):
        raise ValueError(f"Source tree has local changes: {name}")


def prepare(env):
    prepare_sources(source_lock(), env)
    print("Pinned sources prepared; no upstream build scripts were executed.")


def prepare_sources(lock, env):
    for name, item in lock.items():
        if name == "schema":
            continue
        path = managed(f"sources/{name}")
        path.mkdir(parents=True, exist_ok=True)
        git = git_command(env)
        if not (path / ".git").exists():
            if any(path.iterdir()):
                raise ValueError(f"Source directory is not empty: {path}")
            run([*git, "init", "."], f"{name}-init", env, path)
            run([*git, "remote", "add", "origin", item["url"]], f"{name}-remote", env, path)
        if capture([*git, "remote", "get-url", "origin"], path, env) != item["url"]:
            raise ValueError(f"Source remote mismatch: {name}")
        if capture([*git, "status", "--porcelain", "--untracked-files=all", "--ignored"], path, env):
            raise ValueError(f"Refusing to overwrite modified source: {name}")
        probe = subprocess.run([*git, "rev-parse", "--verify", "HEAD"], cwd=path, env=env,
                               capture_output=True, text=True, check=False)
        if probe.returncode or probe.stdout.strip() != item["revision"]:
            run([*git, "fetch", "--depth=1", "--no-tags", "origin", item["revision"]],
                f"{name}-fetch", env, path)
            run([*git, "-c", "submodule.recurse=false", "checkout", "--detach", item["revision"]],
                f"{name}-checkout", env, path)
        verify_source(name, item, env)


def verify_sources(env):
    for name, item in source_lock().items():
        if name != "schema":
            verify_source(name, item, env)
