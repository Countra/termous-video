"""消费已提交的 libplacebo SDK 执行测试，不触发依赖下载或重建。"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "3rd"))
from lib.platforms import host_target, toolchain
from lib.process import environment
from lib.sdk_manifest import verify_manifest
from lib.placebo.checks import verify_codec_link, verify_link
from lib.placebo.manifest import verify_component


def main():
    parser = argparse.ArgumentParser(description="Test an installed static libplacebo SDK")
    parser.add_argument("--sdk-dir", type=Path)
    args = parser.parse_args()
    target = host_target()
    sdk = (args.sdk_dir or ROOT / "sdk" / target).absolute() / "placebo"
    verify_manifest(sdk.parent, target, current_recipe=False)
    verify_component(sdk, target, current_recipe=False)
    env = environment()
    tools = toolchain(target, env, for_build=False)
    verify_link(sdk, target, tools, env)
    verify_codec_link(sdk.parent, sdk, target, tools, env)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"libplacebo SDK checks failed: {error}", file=sys.stderr)
        sys.exit(1)
