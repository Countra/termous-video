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
from placebo_fixture import fixture as placebo_fixture

spec = importlib.util.spec_from_file_location("sdk_entry", TOOLS / "sdk.py")
sdk_entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdk_entry)
spec = importlib.util.spec_from_file_location("placebo_entry", TOOLS.parent / "scripts/check-placebo.py")
placebo_entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(placebo_entry)
spec = importlib.util.spec_from_file_location("go_entry", TOOLS.parent / "scripts/check.py")
go_entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(go_entry)
COMMIT = "1" * 40


def fixture(directory, target):
    placebo_fixture(directory / "placebo", target)
    lock = source_lock()
    files = {
        "lib/libtermous_video_yuv.a": b"!<arch>\n",
        "include/termous_video_symbols.h": b"prefix", "symbols/rename.map": b"A termous_video_A\n",
        "include/libyuv.h": b"yuv", "include/libyuv/convert.h": b"convert",
        "licenses/libyuv-LICENSE": b"license",
        "licenses/libyuv-PATENTS": b"patents", "README.md": b"sdk",
        "build-lock.json": json.dumps(lock).encode(),
    }
    files.update({"lib/libtermous_video_x264.a": b"!<arch>\n", "include/x264.h": b"api",
                  "include/x264_config.h": b"config", "licenses/x264-COPYING": b"license"})
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    data = {"schema": 3, "platform": target, "scope": "video_dependencies", "build_type": "Release",
            "components": {"placebo": "placebo/manifest.json"},
            "library_type": "static", "sources": lock, "source_commit": COMMIT,
            "source_dirty": False, "isolation": {"version": 1, "prefix": "termous_video_", "symbols": 1}, "recipe_sha256": sdk_manifest.recipe_hash(),
            "verification": {"c_link": True, "whole_archive_link": True, "cgo_link": True,
                             "synthetic_smoke": True, "desktop_captured": False, "placebo_coexistence": True,
                             "x264_encode": True, "video_decode": False},
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

    def test_go_checks_use_go_macos_baseline_without_changing_other_targets(self):
        for target in TARGETS:
            with self.subTest(target=target):
                sdk = self.build / target
                fixture(sdk, target)
                # 模拟 runner 默认版本比项目基线高；非 macOS 检查不修改此环境设置。
                with patch.dict(go_entry.os.environ, {"MACOSX_DEPLOYMENT_TARGET": "15.0"}):
                    env = go_entry.go_environment(sdk, target)
                    self.assertEqual(env["MACOSX_DEPLOYMENT_TARGET"],
                                     "13.0" if target.startswith("darwin/") else "15.0")
                    self.assertEqual(go_entry.os.environ["MACOSX_DEPLOYMENT_TARGET"], "15.0")

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

    def test_install_replaces_old_artifacts_without_leaving_removed_libraries(self):
        target = TARGETS[0]
        installed = self.root / "sdk" / target
        (installed / "lib").mkdir(parents=True)
        (installed / "lib/libtermous_video_openh264.a").write_bytes(b"old archive")
        (installed / "manifest.json").write_text(json.dumps({
            "schema": 2, "scope": "video_dependencies", "platform": target}))
        staged = self.build / "new"
        fixture(staged, target)
        sdk_install.install_sdk(target, staged)
        self.assertFalse((installed / "lib/libtermous_video_openh264.a").exists())
        sdk_manifest.verify_manifest(installed, target, COMMIT)

    def test_install_rejects_invalid_old_metadata_without_moving_files(self):
        target = TARGETS[0]
        installed = self.root / "sdk" / target
        installed.mkdir(parents=True)
        marker = installed / "old-library.a"
        marker.write_bytes(b"original SDK")
        manifest = installed / "manifest.json"
        staged = self.build / "new"
        fixture(staged, target)
        for metadata in ([], None, "invalid", {"platform": target}):
            with self.subTest(metadata=metadata):
                manifest.write_text(json.dumps(metadata), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Refusing to replace"):
                    sdk_install.install_sdk(target, staged)
                self.assertEqual(marker.read_bytes(), b"original SDK")
                self.assertEqual(json.loads(manifest.read_text()), metadata)
                self.assertTrue(staged.is_dir())
                self.assertFalse((self.build / "sdk-backup" / target).exists())

    def test_failed_migration_restores_legacy_sdk_without_partial_new_files(self):
        target = TARGETS[0]
        installed = self.root / "sdk" / target
        (installed / "lib").mkdir(parents=True)
        (installed / "lib/libtermous_video_openh264.a").write_bytes(b"original archive")
        (installed / "manifest.json").write_text(json.dumps({
            "schema": 2, "scope": "video_dependencies", "platform": target}), encoding="utf-8")
        original_files = {p.relative_to(installed): p.read_bytes()
                          for p in sdk_manifest.checked_files(installed)}
        staged = self.build / "new"
        fixture(staged, target)
        original_replace = Path.replace

        def replace(path, destination):
            if path == staged:
                raise OSError("simulated migration failure")
            return original_replace(path, destination)

        with patch.object(Path, "replace", replace), self.assertRaisesRegex(OSError, "migration failure"):
            sdk_install.install_sdk(target, staged)
        self.assertEqual({p.relative_to(installed): p.read_bytes()
                          for p in sdk_manifest.checked_files(installed)}, original_files)
        self.assertTrue(staged.is_dir())
        self.assertFalse((self.build / "sdk-backup" / target).exists())

    def test_obsolete_manifest_schema_is_rejected(self):
        staged = self.build / "obsolete"
        fixture(staged, TARGETS[0])
        path = staged / "manifest.json"
        data = json.loads(path.read_text())
        for version in (1, 2, 4):
            with self.subTest(schema=version):
                data["schema"] = version
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, "build format mismatch"):
                    sdk_manifest.verify_manifest(staged, TARGETS[0], current_recipe=False)

    def test_sdk_rejects_legacy_payload_and_false_decode_claim(self):
        staged = self.build / "mixed"
        fixture(staged, TARGETS[0])
        extra = staged / "include/wels/codec_api.h"
        extra.parent.mkdir()
        extra.write_text("old header")
        path = staged / "manifest.json"
        data = json.loads(path.read_text())
        data["files"] = sdk_manifest.inventory(staged)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "OpenH264"):
            sdk_manifest.verify_manifest(staged, TARGETS[0])
        extra.unlink()
        data["files"] = sdk_manifest.inventory(staged)
        data["verification"]["video_decode"] = True
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "without claiming decoding"):
            sdk_manifest.verify_manifest(staged, TARGETS[0])

    def test_sdk_audit_rejects_incomplete_publication(self):
        fixture(self.root / "sdk" / TARGETS[0], TARGETS[0])
        with patch.object(sdk_entry, "PROJECT_ROOT", self.root), self.assertRaises(ValueError):
            sdk_entry.audit_installed()

    def test_missing_sdk_requires_explicit_allow_unbuilt(self):
        with patch.object(sdk_entry, "PROJECT_ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "have not been published"):
                sdk_entry.audit_installed()
            self.assertFalse(sdk_entry.audit_installed(allow_unbuilt=True))
            with patch.object(sdk_entry, "verify_manifest") as verify:
                sdk_entry.check_sdk(allow_unbuilt=True)
                verify.assert_not_called()

    def test_allow_unbuilt_does_not_skip_an_explicit_missing_sdk(self):
        with self.assertRaisesRegex(ValueError, "Directory does not exist"):
            sdk_entry.check_sdk(self.build / "missing", allow_unbuilt=True)

    def test_old_artifacts_are_reported_as_unbuilt_without_accepting_mixed_sets(self):
        for target in TARGETS:
            directory = self.root / "sdk" / target
            directory.mkdir(parents=True)
            (directory / "manifest.json").write_text(json.dumps({"schema": 2,
                "scope": "video_dependencies", "platform": target, "sources": {"openh264": {}}}))
        with patch.object(sdk_entry, "PROJECT_ROOT", self.root):
            self.assertFalse(sdk_entry.audit_installed(allow_unbuilt=True))
            fixture(self.root / "sdk" / TARGETS[0], TARGETS[0])
            with self.assertRaises(ValueError):
                sdk_entry.audit_installed(allow_unbuilt=True)

    def test_installed_set_rejects_different_build_generations(self):
        for target in TARGETS:
            fixture(self.root / "sdk" / target, target)
        manifest = self.root / "sdk" / TARGETS[-1] / "manifest.json"
        data = json.loads(manifest.read_text())
        data["source_commit"] = "2" * 40
        manifest.write_text(json.dumps(data))
        with patch.object(sdk_entry, "PROJECT_ROOT", self.root), self.assertRaisesRegex(ValueError, "same source"):
            sdk_entry.audit_installed()

    def test_allow_unbuilt_does_not_hide_corrupt_new_sdk(self):
        for target in TARGETS:
            fixture(self.root / "sdk" / target, target)
        (self.root / "sdk" / TARGETS[0] / "include/x264.h").unlink()
        with patch.object(sdk_entry, "PROJECT_ROOT", self.root), self.assertRaisesRegex(ValueError, "digest"):
            sdk_entry.check_sdk(allow_unbuilt=True)

    def test_encoder_cache_key_changes_when_archive_changes_in_place(self):
        staged = self.build / "sdk"
        fixture(staged, TARGETS[0])
        before = sdk_manifest.sdk_fingerprint(staged)
        self.assertEqual(before, sdk_manifest.sdk_fingerprint(staged))
        archive = staged / "lib/libtermous_video_x264.a"
        archive.write_bytes(archive.read_bytes() + b"new object")
        self.assertNotEqual(before, sdk_manifest.sdk_fingerprint(staged))

    def test_rejects_tampering_and_missing_library(self):
        staged = self.build / "sdk"
        fixture(staged, TARGETS[0])
        (staged / "include/libyuv.h").write_text("modified")
        with self.assertRaisesRegex(ValueError, "digest"):
            sdk_manifest.verify_manifest(staged, TARGETS[0])
        fixture(staged, TARGETS[0])
        (staged / "lib/libtermous_video_yuv.a").unlink()
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
        for name, content in (("lib/openh264.dll", b"dll"), ("lib/libtermous_video_yuv.a", b"!<thin>\n")):
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
        (installed / "lib/libtermous_video_yuv.a").write_bytes(b"broken")
        with patch.object(sdk_entry, "PROJECT_ROOT", self.root), self.assertRaisesRegex(ValueError, "digest"):
            sdk_entry.audit_installed()

    def test_missing_component_is_never_accepted(self):
        target = TARGETS[0]
        installed = self.root / "sdk" / target
        fixture(installed, target)
        shutil.rmtree(installed / "placebo")
        with patch.object(placebo_entry, "ROOT", self.root), \
                patch.object(placebo_entry, "host_target", return_value=target), \
                patch.object(sys, "argv", ["check-placebo.py"]), \
                patch.object(placebo_entry, "verify_link") as link:
            with self.assertRaises(ValueError):
                placebo_entry.main()
            path = installed / "manifest.json"
            data = json.loads(path.read_text())
            del data["components"]
            data["files"] = sdk_manifest.inventory(installed)
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "requires exactly"):
                placebo_entry.main()
            link.assert_not_called()

    def test_recipe_digest_tracks_objective_c_sources(self):
        recipe = self.root / "recipe"
        recipe.mkdir()
        with patch.object(sdk_manifest, "TOOLS_ROOT", recipe), \
                patch.object(sdk_manifest, "PROJECT_ROOT", self.root):
            previous = sdk_manifest.recipe_hash()
            for name in ("probe.m", "probe.mm"):
                (recipe / name).write_text("int probe(void) { return 1; }\n")
                current = sdk_manifest.recipe_hash()
                self.assertNotEqual(previous, current)
                previous = current

    def test_malformed_metadata_has_explicit_error(self):
        staged = self.build / "sdk"
        for metadata in ([], None, {"schema": 2}):
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
