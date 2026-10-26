"""编译独立静态库，验证后才安装到平台 SDK。"""

import json
import shutil
import tempfile
from pathlib import Path

from .layout import BUILD_ROOT, TOOLS_ROOT, managed
from .platforms import toolchain
from .process import capture, run
from .sdk_install import install_sdk
from .sdk_link import verify_link
from .sdk_manifest import inventory, recipe_hash, source_record, verify_manifest
from .sources import source_lock, verify_sources
from .symbols import isolate, symbol_tools


def build_sdk(target, jobs, env):
    recipe = recipe_hash()
    lock = source_lock()
    verify_sources(env)
    # 编译器探测会前置 Xcode 目录；提前固定符号工具，避免切换到其同名旧版本。
    isolation_tools = symbol_tools(env)
    tools = toolchain(target, env)
    record = source_record(managed("logs/source-status.log"))
    expected = env.get("SOURCE_COMMIT")
    if expected and (record["source_commit"] != expected or record["source_dirty"]):
        raise ValueError("Publication builds require the selected commit and a clean working tree")
    output = managed(f"out/{target}")
    command = [tools["cmake"], "-S", str(TOOLS_ROOT), "-B", str(output), "-G", "Ninja",
               "-DCMAKE_BUILD_TYPE=Release", f"-DTERMOUS_TARGET={target}",
               f"-DCMAKE_C_COMPILER={tools['cc']}", f"-DCMAKE_CXX_COMPILER={tools['cxx']}",
               f"-DCMAKE_MAKE_PROGRAM={tools['ninja']}"]
    if target.startswith("darwin/"):
        command += [f"-DCMAKE_OSX_SYSROOT={tools['sdk']}", "-DCMAKE_OSX_ARCHITECTURES=arm64",
                    "-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0", f"-DCMAKE_ASM_COMPILER={tools['cc']}"]
    else:
        command.append(f"-DCMAKE_ASM_NASM_COMPILER={tools['nasm']}")
    run(command, "configure", env)
    run([tools["cmake"], "--build", output, "--parallel", str(jobs)], "build", env)
    parent = managed(f"install/{target}")
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-", dir=parent) as temporary:
        staged = Path(temporary)
        run([tools["cmake"], "--install", output, "--prefix", staged], "install-stage", env)
        isolation = isolate(staged, target, isolation_tools, env)
        licenses = staged / "licenses"
        licenses.mkdir()
        for dependency, filename, name in (("openh264", "LICENSE", "OpenH264-LICENSE"),
                                           ("libyuv", "LICENSE", "libyuv-LICENSE"),
                                           ("libyuv", "PATENTS", "libyuv-PATENTS")):
            shutil.copyfile(managed(f"sources/{dependency}/{filename}"), licenses / name)
        shutil.copyfile(TOOLS_ROOT / "build-lock.json", staged / "build-lock.json")
        (staged / "README.md").write_text(
            f"# Video dependency SDK: {target}\n\n"
            "Separate private static archives: libtermous_video_openh264.a and libtermous_video_yuv.a.\n\n"
            "Include termous_video_symbols.h before third-party headers. Headers are in include/.\n\n"
            f"OpenH264 {lock['openh264']['version']} includes encoding and decoding; libyuv excludes JPEG. "
            "Both libraries retain architecture-specific SIMD paths.\n\n"
            "See the repository 3rd/README.md for compiler and linker requirements. "
            "This SDK does not provide a production Go API.\n", encoding="utf-8")
        verification = verify_link(staged, target, tools, env)
        verify_sources(env)
        if source_record() != record or recipe_hash() != recipe:
            raise ValueError("Source checkout or build recipe changed during the build")
        data = {"schema": 2, "isolation": isolation, "scope": "video_dependencies", "platform": target,
                "library_type": "static", "build_type": "Release", "sources": lock,
                "recipe_sha256": recipe, "verification": verification, **record,
                "toolchain": {key: capture([tools[key], "--version"], BUILD_ROOT, env).splitlines()[0]
                              for key in ("cc", "cxx", "cmake")}, "files": inventory(staged)}
        (staged / "manifest.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify_manifest(staged, target, expected)
        install_sdk(target, staged)
    print(f"Verified SDK installed: sdk/{target}")
