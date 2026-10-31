"""只隔离依赖自身定义的符号，系统及 C++ 运行时的外部引用保持原名。"""

import re
import shutil
from pathlib import Path

from .layout import BUILD_ROOT
from .coff_bss import normalize_archive
from .process import capture, run

PREFIX = "termous_video_"
ENCODER_ARCHIVES = {"libx264.a": "libtermous_video_x264.a",
                    "libyuv.a": "libtermous_video_yuv.a"}
ARCHIVES = {**ENCODER_ARCHIVES, "libopenh264.a": "libtermous_video_openh264.a"}
HEADER = "termous_video_symbols.h"


def symbol_tools(env):
    result = {}
    for name in ("nm", "objcopy"):
        tool = shutil.which(env.get("LLVM_" + name.upper(), "llvm-" + name), path=env.get("PATH"))
        if not tool:
            raise ValueError(f"Required LLVM tool not found: llvm-{name}")
        tool = str(Path(tool).absolute())
        version = capture([tool, "--version"], BUILD_ROOT, env)
        match = re.search(r"(?:LLVM version|version) (\d+)", version)
        if not match or int(match[1]) < 18:
            raise ValueError(f"LLVM 18 or newer is required: {tool}\nReported version:\n{version or '(empty)'}")
        result[name] = tool
    return result


def read_symbols(archive, tools, env, *, defined):
    output = capture([tools["nm"], "-g", "--defined-only" if defined else "--undefined-only",
                      "--format=just-symbols", archive], BUILD_ROOT, env)
    symbols = {line for line in output.splitlines() if line and not line.endswith(":" )}
    if any(any(c.isspace() for c in symbol) for symbol in symbols):
        raise ValueError(f"Unexpected symbol spelling in {archive}")
    return symbols


def private_name(symbol, target):
    # Mach-O 的前导下划线属于对象格式修饰，必须保留在私有前缀之外。
    if target.startswith("darwin/") and symbol.startswith("_"):
        return "_" + PREFIX + symbol[1:]
    return PREFIX + symbol


def isolate(sdk, target, tools, env):
    sdk = Path(sdk)
    definitions = {name: read_symbols(sdk / "lib" / name, tools, env, defined=True)
                   for name in ARCHIVES}
    originals = set().union(*definitions.values())
    if not originals or any(PREFIX in name for name in originals):
        raise ValueError("Expected non-empty, unmodified dependency archives")
    mapping = {name: private_name(name, target) for name in sorted(originals)}
    metadata = sdk / "symbols"
    metadata.mkdir()
    map_file = metadata / "rename.map"
    map_file.write_text("".join(f"{name} {private}\n" for name, private in mapping.items()), encoding="utf-8")
    macros = []
    for name in mapping:
        identifier = name[1:] if target.startswith("darwin/") and name.startswith("_") else name
        # C++ 修饰名和对象格式辅助符号只在归档内重命名，不污染预处理器。
        if re.fullmatch(r"[A-Za-z][A-Za-z_0-9]*", identifier):
            macros.append(f"#define {identifier} {PREFIX}{identifier}\n")
    (sdk / "include" / HEADER).write_text(
        "// 自动生成：只供本 SDK 原生封装使用，必须先于第三方头文件包含。\n#pragma once\n" + "".join(macros),
        encoding="utf-8")
    bss_sections = 0
    for original, private in ARCHIVES.items():
        run([tools["objcopy"], "--enable-deterministic-archives", "--redefine-syms=" + str(map_file),
             sdk / "lib" / original, sdk / "lib" / private], "isolate-" + original, env)
        if target == "windows/amd64":
            bss_sections += normalize_archive(sdk / "lib" / private)
        actual = read_symbols(sdk / "lib" / private, tools, env, defined=True)
        unresolved = read_symbols(sdk / "lib" / private, tools, env, defined=False)
        if actual != {mapping[s] for s in definitions[original]} or unresolved & originals:
            raise ValueError(f"Incomplete symbol isolation: {private}")
    # 所有归档全部验证后才移除暂存区原件，安装失败不会影响已有 SDK。
    for original in ARCHIVES:
        (sdk / "lib" / original).unlink()
    return {"version": 1, "prefix": PREFIX, "symbols": len(mapping), "coff_bss_sections": bss_sections,
            "tools": {key: capture([tool, "--version"], BUILD_ROOT, env).splitlines()
                      for key, tool in tools.items()}}
