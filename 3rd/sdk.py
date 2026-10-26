"""校验及装配同一提交生成的三平台 SDK，不下载或执行依赖。"""

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.pycache_prefix = str(Path(__file__).resolve().parent.parent / "build/cache/pycache")

from lib.layout import PROJECT_ROOT, managed
from lib.platforms import TARGETS
from lib.sdk_install import install_sdk
from lib.sdk_manifest import checked_files, verify_manifest


def audit_installed():
    count = 0
    for target in TARGETS:
        directory = PROJECT_ROOT / "sdk" / target
        if directory.exists() or directory.is_symlink():
            verify_manifest(directory, target, current_recipe=False)
            count += 1
            print(f"Installed SDK integrity verified: {target}")
    if not count:
        print("No installed SDKs; integrity checks will run after the first SDK publication.")


def assemble(artifacts, source_commit):
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Source commit must be a full SHA")
    checked_files(artifacts)
    expected = {"native-sdk-" + target.replace("/", "-") for target in TARGETS}
    if {p.name for p in artifacts.iterdir()} != expected:
        raise ValueError("Exactly one SDK artifact per target is required")
    verified = []
    for target in TARGETS:
        directory = artifacts / ("native-sdk-" + target.replace("/", "-"))
        verify_manifest(directory, target, source_commit)
        verified.append((target, directory))
    parent = managed("assemble")
    parent.mkdir(parents=True, exist_ok=True)
    for target, directory in verified:
        with tempfile.TemporaryDirectory(prefix="sdk-", dir=parent) as temporary:
            staged = Path(temporary)
            shutil.copytree(directory, staged, dirs_exist_ok=True)
            install_sdk(target, staged)


def main():
    parser = argparse.ArgumentParser(description="Verify or assemble video dependency SDKs.")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("audit", help="Check installed SDK integrity without requiring the latest source recipe")
    assemble_parser = commands.add_parser("assemble")
    assemble_parser.add_argument("--artifacts-dir", type=Path, required=True)
    assemble_parser.add_argument("--source-commit", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--sdk-dir", type=Path, required=True)
    verify_parser.add_argument("--target", choices=TARGETS, required=True)
    verify_parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.action == "audit":
        audit_installed()
    elif args.action == "assemble":
        assemble(args.artifacts_dir.resolve(), args.source_commit)
    else:
        verify_manifest(args.sdk_dir, args.target, args.source_commit)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"SDK verification failed: {error}", file=sys.stderr)
        sys.exit(1)
