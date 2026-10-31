"""校验及装配同一提交生成的三平台 SDK，不下载或执行依赖。"""

import argparse
import json
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


def check_sdk(directory=None, *, allow_unbuilt=False):
    from lib.platforms import host_target, toolchain
    from lib.process import environment
    from lib.sdk_link import verify_link
    from lib.placebo.checks import verify_link as verify_placebo, verify_codec_link

    root = PROJECT_ROOT / "sdk"
    if allow_unbuilt and directory is None and not audit_installed(allow_unbuilt=True):
        print("Native x264 SDK checks were not run; rebuild and publish the SDK first.")
        return
    target = host_target()
    sdk = Path(directory).absolute() if directory is not None else root / target
    verify_manifest(sdk, target, current_recipe=False)
    env = environment()
    tools = toolchain(target, env, for_build=False)
    verify_link(sdk, target, tools, env)
    verify_placebo(sdk / "placebo", target, tools, env)
    verify_codec_link(sdk, sdk / "placebo", target, tools, env)
    print(f"SDK native encoding and coexistence checks passed: {target}")


def audit_installed(*, allow_unbuilt=False):
    root = PROJECT_ROOT / "sdk"
    if not root.exists() and not root.is_symlink():
        if not allow_unbuilt:
            raise ValueError("SDKs have not been published; run the SDK build workflow")
        print("SDKs have not been published; integrity checks were not run.")
        return False
    if allow_unbuilt:
        # 旧二进制保留到 CI 整套替换；只报告待重建，不兼容或认可其校验格式。
        checked_files(root)
        manifests = [json.loads((root / target / "manifest.json").read_text(encoding="utf-8"))
                     for target in TARGETS]
        if all(isinstance(data, dict) and data.get("schema") == 2
               and data.get("scope") == "video_dependencies" and data.get("platform") == target
               and isinstance(data.get("sources"), dict) and "openh264" in data["sources"]
               for target, data in zip(TARGETS, manifests)):
            print("Existing SDK artifacts predate x264; integrity was not verified. Run the SDK build workflow.")
            return False
    provenance = None
    for target in TARGETS:
        data = verify_manifest(root / target, target, current_recipe=False)
        current = (data["source_commit"], data["source_dirty"], data["recipe_sha256"], data["sources"])
        if provenance is not None and current != provenance:
            raise ValueError("Installed SDKs must come from the same source and recipe")
        provenance = current
        print(f"Installed SDK integrity verified: {target}")
    return True


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
    audit_parser = commands.add_parser("audit", help="Check installed SDK integrity without requiring the latest source recipe")
    audit_parser.add_argument("--allow-unbuilt", action="store_true", help="Report unpublished x264 artifacts without claiming verification")
    check_parser = commands.add_parser("check", help="Run native SDK encoding, rendering and link checks")
    check_parser.add_argument("--sdk-dir", type=Path)
    check_parser.add_argument("--allow-unbuilt", action="store_true", help="Report unpublished x264 artifacts without running native checks")
    assemble_parser = commands.add_parser("assemble")
    assemble_parser.add_argument("--artifacts-dir", type=Path, required=True)
    assemble_parser.add_argument("--source-commit", required=True)
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("--sdk-dir", type=Path, required=True)
    verify_parser.add_argument("--target", choices=TARGETS, required=True)
    verify_parser.add_argument("--source-commit")
    args = parser.parse_args()
    if args.action == "audit":
        audit_installed(allow_unbuilt=args.allow_unbuilt)
    elif args.action == "check":
        check_sdk(args.sdk_dir, allow_unbuilt=args.allow_unbuilt)
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
