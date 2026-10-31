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
from lib.sdk_manifest import checked_files, inventory, verify_manifest
from lib.placebo.manifest import verify_component


def check_sdk(directory=None, *, allow_unbuilt=False):
    from lib.platforms import host_target, toolchain
    from lib.process import environment
    from lib.sdk_link import verify_link
    from lib.placebo.checks import verify_link as verify_placebo, verify_codec_link

    root = PROJECT_ROOT / "sdk"
    if allow_unbuilt and directory is None and not audit_installed(allow_unbuilt=True):
        print("Native codec SDK checks were not run; rebuild and publish the SDK first.")
        return
    target = host_target()
    sdk = Path(directory).absolute() if directory is not None else root / target
    verify_manifest(sdk, target, current_recipe=False)
    env = environment()
    tools = toolchain(target, env, for_build=False)
    verify_link(sdk, target, tools, env)
    verify_placebo(sdk / "placebo", target, tools, env)
    verify_codec_link(sdk, sdk / "placebo", target, tools, env)
    print(f"SDK native encoding, decoding and coexistence checks passed: {target}")


def audit_installed(*, allow_unbuilt=False):
    root = PROJECT_ROOT / "sdk"
    if not root.exists() and not root.is_symlink():
        raise ValueError("SDKs have not been published; run the SDK build workflow")
    if allow_unbuilt:
        # 旧二进制保留到 CI 整套替换；核对完整性和同代来源后只报告待重建。
        checked_files(root)
        manifests = [json.loads((root / target / "manifest.json").read_text(encoding="utf-8"))
                     for target in TARGETS]
        generation = manifests[0].get("schema") if isinstance(manifests[0], dict) else None
        dependencies = {2: {"schema", "openh264", "libyuv"}, 3: {"schema", "x264", "libyuv"}}
        if type(generation) is int and generation in dependencies and all(isinstance(data, dict) and data.get("schema") == generation
               and data.get("scope") == "video_dependencies" and data.get("platform") == target
               and data.get("library_type") == "static" and data.get("build_type") == "Release"
               and isinstance(data.get("sources"), dict) and set(data["sources"]) == dependencies[generation]
               for target, data in zip(TARGETS, manifests)):
            provenance = None
            codec = "openh264" if generation == 2 else "x264"
            libraries = {f"lib/libtermous_video_{codec}.a", "lib/libtermous_video_yuv.a"}
            required = {"include/libyuv.h", "include/libyuv/convert.h", "include/termous_video_symbols.h",
                        "licenses/libyuv-LICENSE", "licenses/libyuv-PATENTS", "symbols/rename.map",
                        "README.md", "build-lock.json", "placebo/manifest.json"} | libraries
            required.update({"include/wels/codec_api.h", "include/wels/codec_app_def.h", "include/wels/codec_def.h",
                             "include/wels/codec_ver.h", "licenses/OpenH264-LICENSE"} if generation == 2 else
                            {"include/x264.h", "include/x264_config.h", "licenses/x264-COPYING"})
            for target, data in zip(TARGETS, manifests):
                payload = inventory(root / target)
                if data.get("files") != payload or not required <= payload.keys():
                    raise ValueError("Previous SDK file digest or required payload mismatch")
                if {name for name in payload if name.startswith("lib/")} != libraries:
                    raise ValueError("Previous SDK contains mixed or unexpected archives")
                for name in sorted(libraries):
                    with (root / target / name).open("rb") as stream:
                        if stream.read(8) != b"!<arch>\n":
                            raise ValueError(f"Previous SDK requires regular static archives: {name}")
                if data.get("components") != {"placebo": "placebo/manifest.json"}:
                    raise ValueError("Previous SDK requires the libplacebo SDK component")
                verify_component(root / target / "placebo", target, current_recipe=False)
                lock = json.loads((root / target / "build-lock.json").read_text(encoding="utf-8"))
                if lock != data["sources"]:
                    raise ValueError("Previous SDK dependency lock mismatch")
                current = tuple(data.get(key) for key in
                                ("source_commit", "source_dirty", "recipe_sha256", "sources"))
                if (not isinstance(current[0], str) or not re.fullmatch(r"[0-9a-f]{40}", current[0])
                        or not isinstance(current[1], bool) or not isinstance(current[2], str)
                        or not re.fullmatch(r"[0-9a-f]{64}", current[2])
                        or (provenance is not None and current != provenance)):
                    raise ValueError("Previous SDKs must come from the same source and recipe")
                provenance = current
            print("Existing SDKs lack cross-codec decoding verification; rebuild the complete SDK set. Native checks were not run.")
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
    audit_parser.add_argument("--allow-unbuilt", action="store_true", help="Report complete previous-generation SDKs as requiring rebuild")
    check_parser = commands.add_parser("check", help="Run native SDK encoding, decoding, rendering and link checks")
    check_parser.add_argument("--sdk-dir", type=Path)
    check_parser.add_argument("--allow-unbuilt", action="store_true", help="Report complete previous-generation SDKs as requiring rebuild")
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
