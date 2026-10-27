"""三个受支持的本机构建目标；Windows 限制为 MinGW-w64 GCC。"""

import os
import platform
import shutil
from pathlib import Path

from .layout import BUILD_ROOT
from .process import capture

TARGETS = ("windows/amd64", "linux/amd64", "darwin/arm64")


def host_target():
    arch = platform.machine().lower()
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(arch, arch)
    return f"{platform.system().lower()}/{arch}"


def toolchain(target, env, *, for_build=True):
    if target not in TARGETS or target != host_target():
        raise ValueError(f"Only native builds are supported: host={host_target()}, target={target}")
    names = {"go": "go", "cc": "gcc", "cxx": "g++",
             "inspect": "objdump"}
    if for_build:
        names.update(cmake="cmake", ninja="ninja")
    if target.startswith("darwin/"):
        names.update(cc="clang", cxx="clang++", inspect="otool")
    elif for_build:
        names["nasm"] = "nasm"
    tools = {}
    for key, name in names.items():
        if target.startswith("darwin/") and key in ("cc", "cxx", "inspect"):
            value = capture(["xcrun", "--find", name], BUILD_ROOT, env)
        else:
            value = shutil.which(env.get({"cc": "CC", "cxx": "CXX"}.get(key, ""), name),
                                 path=env.get("PATH"))
        if not value or not Path(value).is_file():
            raise RuntimeError(f"Required tool not found: {name}")
        tools[key] = str(Path(value).absolute())
    for key in ("cc", "cxx"):
        triplet = capture([tools[key], "-dumpmachine"], BUILD_ROOT, env)
        valid = {"windows/amd64": triplet == "x86_64-w64-mingw32",
                 "linux/amd64": triplet.startswith("x86_64-") and "linux" in triplet,
                 "darwin/arm64": triplet.startswith(("arm64-", "aarch64-")) and "darwin" in triplet}
        if not valid[target]:
            raise RuntimeError(f"Compiler target mismatch: {triplet}")
        if target.startswith("windows/"):
            macros = capture([tools[key], "-dM", "-E", "-x", "c", "-include", "_mingw.h", "-"],
                             BUILD_ROOT, env, input_text="")
            if "#define __MINGW64__ " not in macros or "#define _UCRT " in macros or "#define __clang__ " in macros:
                raise RuntimeError("Windows SDK requires MinGW64 GCC with MSVCRT; UCRT64 and Clang are unsupported")
    env["PATH"] = str(Path(tools["cc"]).parent) + os.pathsep + env["PATH"]
    if target.startswith("darwin/"):
        tools["sdk"] = capture(["xcrun", "--sdk", "macosx", "--show-sdk-path"], BUILD_ROOT, env)
        env.update(SDKROOT=tools["sdk"], MACOSX_DEPLOYMENT_TARGET="12.0")
    return tools


def link_flags(target):
    if target == "windows/amd64":
        return ["-static", "-lstdc++", "-lwinpthread"]
    if target == "linux/amd64":
        return ["-Wl,-Bstatic", "-lstdc++", "-Wl,-Bdynamic", "-pthread", "-lm"]
    if target == "darwin/arm64":
        return ["-mmacosx-version-min=12.0", "-lc++"]
    raise ValueError(f"Unsupported target: {target}")
