"""覆盖渲染 SDK 的来源、平台边界、动态依赖与验证状态。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.layout import BUILD_ROOT
from lib.placebo import checks, manifest, recipes, review, sources
from lib.placebo.layout import archives, link_description
from lib.platforms import TARGETS
from lib.sdk_manifest import inventory
from placebo_fixture import fixture


class PlaceboTests(unittest.TestCase):
    def setUp(self):
        parent = BUILD_ROOT / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_official_pinned_sources_and_platform_dependencies(self):
        lock = sources.source_lock()
        self.assertEqual(lock["libplacebo"]["url"], "https://code.videolan.org/videolan/libplacebo.git")
        self.assertNotIn("moltenvk", sources.dependencies("windows/amd64"))
        self.assertNotIn("spirv-cross", sources.dependencies("linux/amd64"))
        self.assertIn("cereal", sources.dependencies("darwin/arm64"))
        lock["libplacebo"]["revision"] = "master"
        with self.assertRaises(ValueError):
            sources.validate_lock(lock)

    def test_link_contract_has_only_static_archives_and_expected_backends(self):
        for target in TARGETS:
            description = link_description(target)
            self.assertFalse(description["symbol_renaming"])
            self.assertTrue(all(name.endswith(".a") for name in archives(target)))
        self.assertEqual(link_description("darwin/arm64")["vulkan_loader"], "static_moltenvk")
        self.assertEqual(link_description("linux/amd64")["vulkan_loader"], "system_dlopen")

    def test_all_platform_manifests_and_tampering(self):
        for target in TARGETS:
            sdk = self.root / target
            fixture(sdk, target)
            manifest.verify_component(sdk, target)
            (sdk / "include/libplacebo/config.h").write_text("tampered")
            with self.assertRaisesRegex(ValueError, "digest"):
                manifest.verify_component(sdk, target)

    def update_manifest(self, sdk, change=None):
        path = sdk / "manifest.json"
        data = json.loads(path.read_text())
        data["files"] = inventory(sdk)
        if change:
            change(data)
        path.write_text(json.dumps(data))

    def test_rejects_dll_thin_archive_and_modified_link_flags(self):
        sdk = self.root / "sdk"
        target = "windows/amd64"
        for name, content in (("lib/placebo.dll", b"dll"), ("lib/libplacebo.a", b"!<thin>\n"),
                              ("link.json", b'{"system_flags":["-lplacebo"]}')):
            fixture(sdk, target)
            path = sdk / name
            path.write_bytes(content)
            self.update_manifest(sdk)
            with self.assertRaises(ValueError):
                manifest.verify_component(sdk, target)
            path.unlink()

    def test_unavailable_gpu_is_only_a_valid_report_on_macos(self):
        for target in TARGETS:
            sdk = self.root / target
            fixture(sdk, target)
            self.update_manifest(sdk, lambda d: d["verification"].update(hdr_render="unavailable"))
            if target == "darwin/arm64":
                manifest.verify_component(sdk, target)
            else:
                with self.assertRaisesRegex(ValueError, "rendering"):
                    manifest.verify_component(sdk, target)

    def test_upstream_execution_requires_exact_review_digest(self):
        with patch.object(review, "verify_sources"), self.assertRaisesRegex(ValueError, "approval"):
            review.verify_review("windows/amd64", {}, "0" * 64)

    def test_cgo_cache_key_tracks_archive_and_header_contents(self):
        sdk = self.root / "sdk"
        fixture(sdk, "windows/amd64")
        previous = checks.sdk_fingerprint(sdk)
        self.assertEqual(previous, checks.sdk_fingerprint(sdk))
        for name in ("lib/libplacebo.a", "include/libplacebo/config.h"):
            with self.subTest(name=name):
                path = sdk / name
                content = path.read_bytes()
                path.write_bytes(bytes([content[0] ^ 1]) + content[1:])
                current = checks.sdk_fingerprint(sdk)
                self.assertNotEqual(previous, current)
                previous = current

    def test_runtime_failure_is_not_treated_as_missing_gpu(self):
        binary = self.root / "test"
        for code in (1, 5):
            with self.subTest(code=code), \
                    patch.object(checks, "managed", return_value=self.root / "render.log"), \
                    patch.object(checks.subprocess, "run", return_value=subprocess.CompletedProcess([], code)), \
                    self.assertRaisesRegex(RuntimeError, "failed"):
                checks.run_render(binary, "test", "darwin/arm64", {"PLACEBO_ALLOW_NO_GPU": "1"})

    def test_no_gpu_skip_is_explicit_and_macos_only(self):
        binary = self.root / "test"
        with patch.object(checks, "managed", return_value=self.root / "render.log"), \
                patch.object(checks.subprocess, "run", return_value=subprocess.CompletedProcess([], 77)):
            self.assertEqual(checks.run_render(binary, "test", "darwin/arm64",
                             {"PLACEBO_ALLOW_NO_GPU": "1"}), "unavailable")
            for target, env in (("windows/amd64", {"PLACEBO_ALLOW_NO_GPU": "1"}),
                                ("linux/amd64", {"PLACEBO_ALLOW_NO_GPU": "1"}), ("darwin/arm64", {})):
                with self.assertRaises(RuntimeError):
                    checks.run_render(binary, "test", target, env)

    def test_static_overlay_is_checked_and_preserves_original(self):
        source = self.root / "sources/libplacebo/src/d3d11/meson.build"
        source.parent.mkdir(parents=True)
        original = "dependency('spirv-cross-c-shared', version: '>=0.29.0', required: d3d11)"
        source.write_text(original)
        with patch.object(recipes, "managed", side_effect=lambda p: self.root / p):
            overlay = recipes.overlay_sources()
            self.assertEqual(source.read_text(), original)
            self.assertIn("static: true", (overlay / "src/d3d11/meson.build").read_text())
            source.write_text("unexpected upstream change")
            with self.assertRaisesRegex(ValueError, "declaration changed"):
                recipes.overlay_sources()


if __name__ == "__main__":
    unittest.main()
