"""渲染 SDK 的独立准备、审查和验证入口；不安装到系统或启动采集。"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

sys.pycache_prefix = str(Path(__file__).resolve().parent.parent / "build/cache/pycache")

from lib.layout import managed
from lib.platforms import TARGETS, host_target, toolchain
from lib.process import environment
from lib.placebo.sources import prepare, verify_sources
from lib.placebo.review import REVIEW, review_digest


def main():
    parser = argparse.ArgumentParser(description="Prepare and verify the static libplacebo SDK component")
    parser.add_argument("action", choices=("prepare", "review", "build"))
    parser.add_argument("--target", choices=TARGETS, default=host_target())
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 2, 8))
    parser.add_argument("--accepted-review-sha256", default="")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 128:
        raise ValueError("Jobs must be between 1 and 128")
    env = environment()
    if args.action == "prepare":
        prepare(args.target, env)
    elif args.action == "review":
        verify_sources(args.target, env)
        print(f"Review manifest: {REVIEW}\nSHA256: {review_digest()}")
    else:
        from lib.placebo.build import build_component
        tools = toolchain(args.target, env)
        parent = managed(f"install/placebo/{args.target}")
        parent.mkdir(parents=True, exist_ok=True)
        # 保留本机验证产物；正式 sdk 由统一构建器事务安装。
        output = Path(tempfile.mkdtemp(prefix="verified-", dir=parent)) / "placebo"
        build_component(args.target, args.jobs, env, tools, output, args.accepted_review_sha256)
        print(f"Verified libplacebo component: {output}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"libplacebo SDK build failed: {error}", file=sys.stderr)
        sys.exit(1)
