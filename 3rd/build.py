"""视频依赖的统一跨平台 Python 构建入口。"""

import argparse
import os
import sys
from pathlib import Path

sys.pycache_prefix = str(Path(__file__).resolve().parent.parent / "build/cache/pycache")

from lib.build_sdk import build_sdk
from lib.platforms import TARGETS, host_target
from lib.process import environment
from lib.sources import prepare, verify_sources
from lib.placebo import sources as placebo_sources


def main():
    parser = argparse.ArgumentParser(description="Prepare or build pinned video and libplacebo static SDKs.")
    parser.add_argument("action", choices=("prepare", "build", "verify-sources"))
    parser.add_argument("--target", choices=TARGETS, default=host_target())
    parser.add_argument("--jobs", type=int, default=min(os.cpu_count() or 2, 8))
    parser.add_argument("--accepted-review-sha256", default="")
    parser.add_argument("--staging-only", action="store_true", help="Keep the verified SDK under build/install without replacing sdk")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 128:
        raise ValueError("Jobs must be between 1 and 128")
    env = environment()
    if args.action == "prepare":
        prepare(env)
        placebo_sources.prepare(args.target, env)
    elif args.action == "verify-sources":
        verify_sources(env)
        placebo_sources.verify_sources(args.target, env)
    else:
        build_sdk(args.target, args.jobs, env, args.accepted_review_sha256, staging_only=args.staging_only)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"Video SDK build failed: {error}", file=sys.stderr)
        sys.exit(1)
