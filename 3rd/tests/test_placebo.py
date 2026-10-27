"""覆盖渲染 SDK 的来源、平台边界、动态依赖与验证状态。"""

import ast
import configparser
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
from lib.placebo.layout import GLSLANG_ARCHIVES, archives, link_description
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
        glslang = self.root / "sources/libplacebo/src/glsl/meson.build"
        glslang.parent.mkdir(parents=True)
        glslang_original = ("if glslang_req.auto() and shaderc.found()\n"
                            "elif not glslang_req.disabled()\n"
                            "  glslang = cxx.find_library('SPIRV')\n"
                            "endif\n\ncomponents.set('glslang', glslang.found())\n")
        glslang.write_text(glslang_original)
        with patch.object(recipes, "managed", side_effect=lambda p: self.root / p):
            overlay = recipes.overlay_sources()
            self.assertEqual(source.read_text(), original)
            self.assertEqual(glslang.read_text(), glslang_original)
            self.assertIn("static: true", (overlay / "src/d3d11/meson.build").read_text())
            patched = (overlay / "src/glsl/meson.build").read_text()
            self.assertNotIn("find_library", patched)
            self.assertIn("meson.get_external_property('termous_glslang_libraries')", patched)
            source.write_text("unexpected upstream change")
            with self.assertRaisesRegex(ValueError, "declaration changed"):
                recipes.overlay_sources()
            source.write_text(original)
            glslang.write_text("unexpected upstream change")
            with self.assertRaisesRegex(ValueError, "glslang dependency declaration changed"):
                recipes.overlay_sources()

    def test_all_platform_recipes_bind_pinned_archives_with_spaces_in_path(self):
        tools = {key: key for key in ("meson", "cc", "cxx", "pkgconfig", "sdk")}
        for target in TARGETS:
            with self.subTest(target=target):
                prefix = self.root / "dependencies with spaces" / target
                paths = [prefix / "lib" / name for name in GLSLANG_ARCHIVES]
                paths.append(prefix / "include/glslang/build_info.h")
                for path in paths:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"fixture")
                # Windows 安装步骤还复制上游生成的系统 UCRT 导入归档。
                ucrt = self.root / f"out/{target}/placebo/libplacebo/src/ucrt_math.lib"
                ucrt.parent.mkdir(parents=True)
                ucrt.write_bytes(b"fixture")
                with patch.object(recipes, "managed", side_effect=lambda p: self.root / p), \
                        patch.object(recipes, "overlay_sources", return_value=self.root / "sources"), \
                        patch.object(recipes, "run"):
                    recipes.meson_build(target, prefix, tools, {}, 2)
                config = configparser.ConfigParser()
                config.read(self.root / f"out/{target}/placebo/native.ini", encoding="utf-8")
                actual = ast.literal_eval(config["properties"]["termous_glslang_libraries"])
                self.assertEqual(actual, [path.as_posix() for path in paths[:-1]])

    def test_missing_pinned_glslang_never_falls_back_to_system(self):
        prefix = self.root / "dependencies"
        paths = [prefix / "lib" / name for name in GLSLANG_ARCHIVES]
        paths.append(prefix / "include/glslang/build_info.h")
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        for path in paths:
            with self.subTest(path=path.name), patch.object(recipes, "run") as run, \
                    patch.object(recipes, "overlay_sources") as overlay:
                path.unlink()
                with self.assertRaisesRegex(ValueError, "Pinned glslang installation is incomplete"):
                    recipes.meson_build("darwin/arm64", prefix, {}, {}, 2)
                overlay.assert_not_called()
                run.assert_not_called()
                path.write_bytes(b"fixture")


if __name__ == "__main__":
    unittest.main()
