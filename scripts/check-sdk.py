"""调用方只读校验私有 SDK，无需 LLVM 工具或第三方源码。"""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "3rd"))
from lib.platforms import TARGETS
from lib.sdk_manifest import verify_manifest


def main():
    parser = argparse.ArgumentParser(description="Verify the installed private video SDK")
    parser.add_argument("--target", choices=TARGETS, required=True)
    args = parser.parse_args()
    verify_manifest(ROOT / "sdk" / args.target, args.target, current_recipe=False)
    print(f"Private video SDK verified: {args.target}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Video SDK check failed: {error}", file=sys.stderr)
        sys.exit(1)
