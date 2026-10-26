"""用两种归档顺序验证 RDP 自有依赖与 video 私有依赖，不重建或修改 SDK。"""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "3rd"))
from lib.platforms import host_target, link_flags
from lib.sdk_manifest import verify_manifest
from lib.sdk_link import dynamic_dependencies
from lib.symbols import ARCHIVES, HEADER


def main():
    parser = argparse.ArgumentParser(description="Check independent RDP and video SDKs in one binary")
    parser.add_argument("--rdp-sdk", required=True, type=Path)
    parser.add_argument("--sdk-dir", type=Path)
    args = parser.parse_args()
    target = host_target()
    sdk = (args.sdk_dir or ROOT / "sdk" / target).resolve()
    peer = args.rdp_sdk.resolve(strict=True)
    if verify_manifest(sdk, target, current_recipe=False)["schema"] != 2:
        raise ValueError("Private video SDK is required")
    original = [peer / "lib" / name for name in ARCHIVES]
    private = [sdk / "lib" / name for name in ARCHIVES.values()]
    for path in (*original, peer / "include/wels/codec_api.h", peer / "include/libyuv.h"):
        if not path.is_file():
            raise ValueError(f"RDP SDK is missing a required input: {path}")
    env = os.environ.copy()
    tools = {}
    defaults = {"CC": "clang" if target.startswith("darwin/") else "gcc",
                "CXX": "clang++" if target.startswith("darwin/") else "g++",
                "inspect": "otool" if target.startswith("darwin/") else "objdump"}
    for key, default in defaults.items():
        tool = shutil.which(env.get(key, default))
        if not tool:
            raise ValueError(f"Required tool not found: {default}")
        tools[key] = tool
    work = ROOT / "build/checks/coexist" / target
    work.mkdir(parents=True, exist_ok=True)

    def run(command):
        subprocess.run([str(value) for value in command], cwd=work, env=env, check=True, timeout=120)

    platform_flags = ["-mmacosx-version-min=13.0"] if target.startswith("darwin/") else []
    objects = []
    for label, include in (("original", peer / "include"), ("private", sdk / "include")):
        flags = ["-std=c++17", "-O2", *platform_flags, "-I", include]
        if label == "private":
            flags += ["-include", include / HEADER]
        for kind, source, function in (("smoke", ROOT / "3rd/checks/smoke.cc", "video_sdk_smoke"),
                                      ("binding", ROOT / "scripts/checks/coexist.cc", "video_check_binding")):
            output = work / f"{label}-{kind}.o"
            run([tools["CXX"], *flags, f"-D{function}={label}_{kind}", "-c", source, "-o", output])
            objects.append(output)
    caller = work / "caller.o"
    run([tools["CC"], *platform_flags, "-c", ROOT / "scripts/checks/coexist.c", "-o", caller])
    for label, archives in (("original-first", original + private), ("private-first", private + original)):
        binary = work / (label + (".exe" if target.startswith("windows/") else ""))
        run([tools["CC"], caller, *objects, *archives, *link_flags(target), "-o", binary])
        dynamic_dependencies(binary, target, tools, env)
        run([binary])
        print(f"Combined SDK binding, conversion and codec checks passed: {label}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Combined SDK check failed: {error}", file=sys.stderr)
        sys.exit(1)
