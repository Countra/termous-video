"""消费已安装 SDK 检查 Go 公共库；不下载、不构建第三方依赖。"""

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "3rd"))
from lib.platforms import host_target
from lib.sdk_manifest import verify_manifest
from lib.sdk_link import dynamic_dependencies


def go_environment(sdk, target):
    data = verify_manifest(sdk, target, current_recipe=False)
    if data["schema"] != 2:
        raise ValueError("Private video SDK is required; run the manual SDK workflow first")
    env = os.environ.copy()
    digest = hashlib.sha256((sdk / "manifest.json").read_bytes()).hexdigest()
    env.update(CGO_ENABLED="1", GOTOOLCHAIN="local")
    env["CGO_CXXFLAGS"] = env.get("CGO_CXXFLAGS", "") + f' "-I{(sdk / "include").as_posix()}" -DTERMOUS_VIDEO_SDK_{digest}=1'
    env["CGO_LDFLAGS"] = env.get("CGO_LDFLAGS", "") + f' "-L{(sdk / "lib").as_posix()}"'
    return env


def main():
    parser = argparse.ArgumentParser(description="Test the video library with an existing private SDK")
    parser.add_argument("--sdk-dir", type=Path)
    parser.add_argument("--link", action="store_true")
    parser.add_argument("--race", action="store_true")
    args = parser.parse_args()
    target = host_target()
    sdk = (args.sdk_dir or ROOT / "sdk" / target).resolve()
    env = go_environment(sdk, target)
    output = ROOT / "build/checks/go" / target
    output.mkdir(parents=True, exist_ok=True)
    packages = ["./frame", "./convert", "./h264", "./internal/..."]
    subprocess.run(["go", "test", "-count=1", "-tags=video_native_fixture", *(["-race"] if args.race else []),
                    *packages], cwd=ROOT, env=env, check=True, timeout=180)
    if args.link:
        binary = output / ("video.test.exe" if target.startswith("windows/") else "video.test")
        subprocess.run(["go", "test", "-c", "-tags=video_native_fixture", "-o", str(binary), "./h264"],
                       cwd=ROOT, env=env, check=True, timeout=180)
        inspect = shutil.which("otool" if target.startswith("darwin/") else "objdump")
        if not inspect:
            raise ValueError("Required binary inspection tool is missing")
        print("Dynamic dependencies:", dynamic_dependencies(binary, target, {"inspect": inspect}, env))
    print("Video library checks passed")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Video library checks failed: {error}", file=sys.stderr)
        sys.exit(1)
