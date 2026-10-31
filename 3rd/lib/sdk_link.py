"""验证纯编码链接、跨库编解码、全归档和真实 cgo 调用。"""

import re
import shutil

from .layout import BUILD_ROOT, TOOLS_ROOT, managed
from .platforms import link_flags
from .process import capture, run
from .sdk_manifest import sdk_fingerprint
from .symbols import ARCHIVES, ENCODER_ARCHIVES, HEADER

ENCODER_SOURCES = ("encoder.cc", "pattern.cc")
CHECK_SOURCES = (*ENCODER_SOURCES, "decoder.cc", "smoke.cc")


def dynamic_dependencies(binary, target, tools, env, *, allowed_extra=()):
    if target.startswith("darwin/"):
        output = capture([tools["inspect"], "-L", binary], BUILD_ROOT, env)
        libraries = re.findall(r"^\s+(\S+) \(compatibility version", output, re.MULTILINE)
        valid = libraries and all(p.startswith(("/usr/lib/", "/System/Library/")) for p in libraries)
    else:
        output = capture([tools["inspect"], "-p", binary], BUILD_ROOT, env)
        if target.startswith("windows/"):
            sections = capture([tools["inspect"], "-h", binary], BUILD_ROOT, env)
            bss = re.search(r"^\s*\d+\s+\.bss\s+\S+\s+\S+\s+\S+\s+([0-9a-fA-F]+)", sections, re.MULTILINE)
            if bss and int(bss[1], 16):
                raise RuntimeError("COFF BSS was written to the executable; check SDK symbol isolation")
            libraries = re.findall(r"DLL Name:\s*(\S+)", output)
            allowed = {"kernel32.dll", "msvcrt.dll", "ucrtbase.dll", "advapi32.dll", "user32.dll",
                       "shell32.dll", "ws2_32.dll", "ntdll.dll", "bcrypt.dll"}
            allowed.update(allowed_extra)
            valid = libraries and all(name.lower() in allowed or name.lower().startswith("api-ms-win-")
                                      for name in libraries)
        else:
            libraries = re.findall(r"NEEDED\s+(\S+)", output)
            allowed = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1",
                       "libgcc_s.so.1", "ld-linux-x86-64.so.2"}
            valid = libraries and all(name in allowed for name in libraries)
    if not valid:
        raise RuntimeError(f"Unexpected dynamic dependencies: {libraries}")
    return libraries


def verify_link(sdk, target, tools, env):
    check = managed(f"checks/{target}")
    check.mkdir(parents=True, exist_ok=True)
    includes = ["-I", str(sdk / "include"), "-include", str(sdk / "include" / HEADER)]
    flags = link_flags(target)
    archives = [(sdk / "lib" / name).as_posix() for name in ARCHIVES.values()]
    compile_flags = ["-mmacosx-version-min=12.0"] if target.startswith("darwin/") else []
    objects = []
    for source in CHECK_SOURCES:
        obj = check / source.replace(".cc", ".o")
        run([tools["cxx"], "-std=c++17", "-O2", *compile_flags, *includes, "-c",
             TOOLS_ROOT / "checks" / source, "-o", obj], "smoke-" + source, env)
        objects.append(obj)
    run([tools["cc"], *compile_flags, "-c", TOOLS_ROOT / "checks/caller.c", "-o", check / "caller.o"],
        "smoke-c", env)
    suffix = ".exe" if target.startswith("windows/") else ""
    dependencies = set()
    # 不加入 OpenH264 归档，直接用链接和运行证明编码侧没有解码依赖。
    encoder_entry = check / "encoder-only.o"
    run([tools["cxx"], "-std=c++17", "-O2", *compile_flags, *includes, "-DVIDEO_SDK_ENCODER_ONLY",
         "-c", TOOLS_ROOT / "checks/smoke.cc", "-o", encoder_entry], "encoder-only-cpp", env)
    binary = check / ("sdk-encoder-only" + suffix)
    run([tools["cc"], check / "caller.o", encoder_entry,
         *(check / source.replace(".cc", ".o") for source in ENCODER_SOURCES),
         *(sdk / "lib" / name for name in ENCODER_ARCHIVES.values()), *flags, "-o", binary],
        "sdk-encoder-only-link", env)
    dependencies.update(dynamic_dependencies(binary, target, tools, env))
    run([binary], "sdk-encoder-only-run", env, timeout=30)
    whole = ([flag for archive in archives for flag in ("-Xlinker", "-force_load", "-Xlinker", archive)]
             if target.startswith("darwin/") else ["-Wl,--whole-archive", *archives, "-Wl,--no-whole-archive"])
    for label, libraries in (("sdk-c-link", archives), ("sdk-whole-link", whole)):
        binary = check / (label + suffix)
        run([tools["cc"], check / "caller.o", *objects, *libraries, *flags, "-o", binary], label, env)
        dependencies.update(dynamic_dependencies(binary, target, tools, env))
        run([binary], label + "-run", env, timeout=30)
    cgo = check / "cgo"
    cgo.mkdir(exist_ok=True)
    shutil.copyfile(TOOLS_ROOT / "checks/cgo_main.go.in", cgo / "main.go")
    for name in (*CHECK_SOURCES, "codec_check.h"):
        shutil.copyfile(TOOLS_ROOT / "checks" / name, cgo / name)
    (cgo / "go.mod").write_text("module termous/video/sdkcheck\n\ngo 1.24.0\n", encoding="utf-8")
    # Go 缓存尊重调用端统一设置；未设置时只在本仓库 build 内补齐默认值。
    go_env = env.copy()
    for name, relative in (("GOCACHE", "cache/go/build"), ("GOMODCACHE", "cache/go/mod"),
                           ("GOTMPDIR", "cache/go/tmp")):
        if not go_env.get(name):
            directory = managed(relative)
            directory.mkdir(parents=True, exist_ok=True)
            go_env[name] = str(directory)
    go_env.update(CGO_ENABLED="1", CC=tools["cc"], CXX=tools["cxx"], GOWORK="off",
                  GOTOOLCHAIN="local", GOFLAGS="", GOOS=target.split("/")[0], GOARCH=target.split("/")[1],
                  CGO_CPPFLAGS=f'-DTERMOUS_VIDEO_SDK_{sdk_fingerprint(sdk)}=1 '
                               f'"-I{(sdk / "include").as_posix()}" -include "{(sdk / "include" / HEADER).as_posix()}"',
                  CGO_CFLAGS=" ".join(compile_flags), CGO_CXXFLAGS="-std=c++17 " + " ".join(compile_flags),
                  CGO_LDFLAGS=" ".join([*(f'"{p}"' for p in archives), *flags]))
    binary = check / ("sdk-cgo-link" + suffix)
    run([tools["go"], "build", "-o", binary, "."], "sdk-cgo-link", go_env, cgo)
    dependencies.update(dynamic_dependencies(binary, target, tools, env))
    run([binary], "sdk-cgo-run", env, timeout=30)
    return {"c_link": True, "whole_archive_link": True, "cgo_link": True,
            "synthetic_smoke": True, "desktop_captured": False,
            "x264_encode": True, "encoder_only_link": True, "video_decode": True,
            "decoder": "openh264", "openh264_api": True,
            "system_dependencies": sorted(dependencies)}
