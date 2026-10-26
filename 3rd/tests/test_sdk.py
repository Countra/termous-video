"""覆盖 SDK 篡改、跨平台安装、失败恢复及完整产物组验证。"""

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from lib import sdk_install, sdk_manifest
from lib.platforms import TARGETS
from lib.sources import source_lock

spec = importlib.util.spec_from_file_location("sdk_entry", TOOLS / "sdk.py")
sdk_entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk_entry)
COMMIT = "1" * 40


def fixture(directory, target):
    files = {
        "lib/libopenh264.a": b"!<arch>\n", "lib/libyuv.a": b"!<arch>\n",
        "include/wels/codec_api.h": b"api", "include/wels/codec_app_def.h": b"app",
        "include/wels/codec_def.h": b"def", "include/wels/codec_ver.h": b"version",
        "include/libyuv.h": b"yuv", "include/libyuv/convert.h": b"convert",
        "licenses/OpenH264-LICENSE": b"license", "licenses/libyuv-LICENSE": b"license",
        "licenses/libyuv-PATENTS": b"patents", "README.md": b"sdk",
        "build-lock.json": json.dumps(source_lock()).encode(),
    }
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = {"schema": 1, "platform": target, "scope": "video_dependencies", "build_type": "Release",
            "library_type": "static", "sources": source_lock(), "source_commit": COMMIT,
            "source_dirty": False, "recipe_sha256": sdk_manifest.recipe_hash(),
            "verification": {"c_link": True, "whole_archive_link": True, "cgo_link": True,
                             "synthetic_smoke": True, "desktop_captured": False},
            "files": sdk_manifest.inventory(directory)}
    (directory / "manifest.json").write_text(json.dumps(data), encoding="utf-8")


class SDKTests(unittest.TestCase):
    def setUp(self):
        parent = TOOLS.parent / "build/tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        for change in (patch.object(sdk_install, "PROJECT_ROOT", self.root),
                       patch.object(sdk_install, "BUILD_ROOT", self.build),
                       patch.object(sdk_install, "managed", side_effect=lambda p: self.build / p)):
            change.start()
            self.addCleanup(change.stop)

    def test_install_and_replace_each_target(self):
        for target in TARGETS:
            with self.subTest(target=target):
                for attempt in range(2):
                    staged = self.build / f"install-{target.replace('/', '-')}-{attempt}"
                    fixture(staged, target)
                    sdk_install.install_sdk(target, staged)
                    sdk_manifest.verify_manifest(self.root / "sdk" / target, target, COMMIT)
                    self.assertFalse(staged.exists())
                    self.assertFalse((self.build / "sdk-backup" / target).exists())

    def test_failed_replace_restores_old_sdk(self):
        target = "darwin/arm64"
        old = self.root / "sdk" / target
        staged = self.build / "new"
        fixture(old, target)
        fixture(staged, target)
        original = Path.replace

        def replace(path, destination):
            if path == staged:
                raise OSError("simulated install failure")
            return original(path, destination)

        with patch.object(Path, "replace", replace), self.assertRaisesRegex(OSError, "simulated"):
            sdk_install.install_sdk(target, staged)
        sdk_manifest.verify_manifest(old, target, COMMIT)

    def test_rejects_tampering_and_missing_library(self):
        staged = self.build / "sdk"
        fixture(staged, TARGETS[0])
        (staged / "include/libyuv.h").write_text("modified")
        with self.assertRaisesRegex(ValueError, "digest"):
            sdk_manifest.verify_manifest(staged, TARGETS[0])
        fixture(staged, TARGETS[0])
        (staged / "lib/libyuv.a").unlink()
        with self.assertRaises(ValueError):
            sdk_manifest.verify_manifest(staged, TARGETS[0])

    def test_rejects_wrong_commit_and_missing_verification(self):
        staged = self.build / "sdk"
        fixture(staged, TARGETS[0])
        with self.assertRaisesRegex(ValueError, "selected clean commit"):
            sdk_manifest.verify_manifest(staged, TARGETS[0], "2" * 40)
        manifest = staged / "manifest.json"
        data = json.loads(manifest.read_text())
        data["verification"]["cgo_link"] = False
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "verification"):
            sdk_manifest.verify_manifest(staged, TARGETS[0])

    def test_rejects_dynamic_and_thin_libraries_even_with_updated_digest(self):
        staged = self.build / "sdk"
        fixture(staged, TARGETS[0])
        for name, content in (("lib/openh264.dll", b"dll"), ("lib/libyuv.a", b"!<thin>\n")):
            with self.subTest(name=name):
                path = staged / name
                path.write_bytes(content)
                manifest = staged / "manifest.json"
                data = json.loads(manifest.read_text())
                data["files"] = sdk_manifest.inventory(staged)
                manifest.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    sdk_manifest.verify_manifest(staged, TARGETS[0])
                path.unlink()
                fixture(staged, TARGETS[0])

    def test_all_artifacts_checked_before_install(self):
        incoming = self.build / "incoming"
        incoming.mkdir()
        for target in TARGETS:
            fixture(incoming / ("native-sdk-" + target.replace("/", "-")), target)
        (incoming / "native-sdk-darwin-arm64/include/libyuv.h").write_text("broken")
        with patch.object(sdk_entry, "install_sdk") as install:
            with self.assertRaises(ValueError):
                sdk_entry.assemble(incoming, COMMIT)
            install.assert_not_called()

    def test_assemble_installs_complete_set(self):
        incoming = self.build / "incoming"
        incoming.mkdir()
        for target in TARGETS:
            fixture(incoming / ("native-sdk-" + target.replace("/", "-")), target)
        with patch.object(sdk_entry, "managed", side_effect=lambda p: self.build / p):
            sdk_entry.assemble(incoming, COMMIT)
        for target in TARGETS:
            sdk_manifest.verify_manifest(self.root / "sdk" / target, target, COMMIT)

    def test_integrity_audit_allows_previous_recipe_but_install_rejects_it(self):
        staged = self.build / "sdk"
        fixture(staged, TARGETS[0])
        with patch.object(sdk_manifest, "recipe_hash", return_value="0" * 64):
            sdk_manifest.verify_manifest(staged, TARGETS[0], current_recipe=False)
            with self.assertRaisesRegex(ValueError, "recipe mismatch"):
                sdk_install.install_sdk(TARGETS[0], staged)
        self.assertFalse((self.root / "sdk" / TARGETS[0]).exists())

    def test_installed_sdk_audit_detects_corruption(self):
        installed = self.root / "sdk" / TARGETS[0]
        fixture(installed, TARGETS[0])
        (installed / "lib/libyuv.a").write_bytes(b"broken")
        with patch.object(sdk_entry, "PROJECT_ROOT", self.root), self.assertRaisesRegex(ValueError, "digest"):
            sdk_entry.audit_installed()

    def test_malformed_metadata_has_explicit_error(self):
        staged = self.build / "sdk"
        for metadata in ([], None, {"schema": 1}):
            with self.subTest(metadata=metadata):
                fixture(staged, TARGETS[0])
                (staged / "manifest.json").write_text(json.dumps(metadata))
                with self.assertRaises(ValueError):
                    sdk_manifest.verify_manifest(staged, TARGETS[0])

    def test_rejects_symlink(self):
        staged = self.build / "sdk"
        fixture(staged, TARGETS[0])
        try:
            (staged / "link").symlink_to(staged / "README.md")
        except OSError:
            self.skipTest("Symlink creation is unavailable")
        with self.assertRaisesRegex(ValueError, "Links"):
            sdk_manifest.verify_manifest(staged, TARGETS[0])

    def test_git_staging_preserves_sdk_bytes(self):
        repository = self.build / "git-roundtrip"
        repository.mkdir()
        shutil.copyfile(TOOLS.parent / ".gitattributes", repository / ".gitattributes")
        sdk = repository / "sdk/windows/amd64"
        sdk.mkdir(parents=True)
        content = b"SDK header with CRLF\r\nsecond line\r\n"
        (sdk / "README.md").write_bytes(content)
        for command in (["git", "init", "."], ["git", "-c", "core.autocrlf=true", "add", "."]):
            subprocess.run(command, cwd=repository, capture_output=True, check=True)
        actual = subprocess.check_output(["git", "show", ":sdk/windows/amd64/README.md"], cwd=repository)
        self.assertEqual(actual, content)


if __name__ == "__main__":
    unittest.main()
