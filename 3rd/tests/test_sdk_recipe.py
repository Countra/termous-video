"""验证配方只追踪生产输入，历史兼容不能放宽来源或完整性检查。"""

import hashlib
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import sdk_recipe


class RecipeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tools = Path(temporary.name) / "3rd"
        self.tools.mkdir()

    def write(self, relative, content=b"original\n"):
        path = self.tools / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def compatibility(self, current):
        entry = {"source_commit": "1" * 40, "recipe_sha256": "2" * 64, "inputs_sha256": current}
        data = {"schema": 1, "algorithm": sdk_recipe.ALGORITHM, "legacy": [entry]}
        self.write("sdk-recipe-compat.json", json.dumps(data).encode())
        return data, {"source_commit": entry["source_commit"], "recipe_sha256": entry["recipe_sha256"],
                      "source_dirty": False}

    def test_documentation_tests_and_verification_do_not_change_build_inputs(self):
        self.write("cmake/encoder.cmake")
        original = sdk_recipe.recipe_hash(self.tools)
        for relative in ("README.md", "placebo/README.md", "lib/README.md", "tests/test_build.py",
                         "ci/publish-sdk.py", "check.py", "sdk.py", "checks/encoder.cc",
                         "placebo/checks/render.c", "lib/sdk_manifest.py", "lib/sdk_recipe.py",
                         "lib/sdk_link.py", "lib/placebo/checks.py", "lib/placebo/manifest.py",
                         "lib/__pycache__/process.cpython-312.pyc"):
            with self.subTest(relative=relative):
                self.write(relative)
                self.assertEqual(sdk_recipe.recipe_hash(self.tools), original)
                self.write(relative, b"modified\n")
                self.assertEqual(sdk_recipe.recipe_hash(self.tools), original)

    def test_production_changes_additions_removals_and_renames_change_digest(self):
        for relative in ("build.py", "build-lock.json", "placebo-lock.json", "CMakeLists.txt",
                         "cmake/encoder.cmake", "cmake/config.h.in", "lib/build_sdk.py", "lib/symbols.py",
                         "lib/new_generator.py", "lib/placebo/recipes.py", "placebo/upstream-review.json",
                         "placebo/moltenvk/CMakeLists.txt", "cmake/source.m", "cmake/source.mm"):
            with self.subTest(relative=relative):
                before = sdk_recipe.recipe_hash(self.tools)
                path = self.write(relative)
                added = sdk_recipe.recipe_hash(self.tools)
                self.assertNotEqual(before, added)
                path.write_bytes(b"original\r\n")
                self.assertEqual(added, sdk_recipe.recipe_hash(self.tools))
                path.write_bytes(b"changed\n")
                self.assertNotEqual(added, sdk_recipe.recipe_hash(self.tools))
                path.unlink()
                self.assertEqual(before, sdk_recipe.recipe_hash(self.tools))
        path = self.write("cmake/before.cmake")
        before = sdk_recipe.recipe_hash(self.tools)
        path.rename(path.with_name("after.cmake"))
        self.assertNotEqual(before, sdk_recipe.recipe_hash(self.tools))

    def test_digest_uses_version_and_platform_independent_path_order(self):
        self.write("cmake/a.cmake", b"a\r\n")
        self.write("cmake/Z.cmake", b"Z\n")
        expected = hashlib.sha256(sdk_recipe.ALGORITHM.encode() + b"\0"
                                  + b"3rd/cmake/Z.cmake\0Z\n\0" + b"3rd/cmake/a.cmake\0a\n\0")
        self.assertEqual(expected.hexdigest(), sdk_recipe.recipe_hash(self.tools))

    def test_legacy_recipe_requires_exact_clean_origin_and_unchanged_inputs(self):
        self.write("build.py")
        current = sdk_recipe.recipe_hash(self.tools)
        _, manifest = self.compatibility(current)
        self.assertTrue(sdk_recipe.matches_recipe(self.tools, manifest, current))
        for key, value in (("source_commit", "3" * 40), ("recipe_sha256", "3" * 64),
                           ("source_dirty", True), ("source_dirty", None)):
            with self.subTest(key=key, value=value):
                self.assertFalse(sdk_recipe.matches_recipe(self.tools, manifest | {key: value}, current))
        self.write("build.py", b"new build flags\n")
        self.assertFalse(sdk_recipe.matches_recipe(self.tools, manifest, sdk_recipe.recipe_hash(self.tools)))

    def test_new_recipe_does_not_require_legacy_metadata(self):
        current = sdk_recipe.recipe_hash(self.tools)
        self.assertTrue(sdk_recipe.matches_recipe(self.tools, {"recipe_sha256": current}, current))

    def test_invalid_or_duplicate_compatibility_metadata_fails_closed(self):
        data, manifest = self.compatibility("3" * 64)
        invalid = [[], {}, data | {"schema": True}, data | {"algorithm": "unknown"},
                   data | {"legacy": [None]}, data | {"legacy": data["legacy"] * 2},
                   data | {"legacy": [data["legacy"][0] | {"inputs_sha256": "invalid"}]}]
        for value in invalid:
            with self.subTest(value=value):
                self.write("sdk-recipe-compat.json", json.dumps(value).encode())
                with self.assertRaises(ValueError):
                    sdk_recipe.matches_recipe(self.tools, manifest, "3" * 64)

    def test_unreadable_compatibility_metadata_has_an_explicit_error(self):
        _, manifest = self.compatibility("3" * 64)
        path = self.tools / "sdk-recipe-compat.json"
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Cannot read SDK recipe compatibility metadata"):
            sdk_recipe.matches_recipe(self.tools, manifest, "3" * 64)
        for content in (b"{", b"\xff"):
            self.write("sdk-recipe-compat.json", content)
            with self.assertRaisesRegex(ValueError, "Cannot read SDK recipe compatibility metadata"):
                sdk_recipe.matches_recipe(self.tools, manifest, "3" * 64)

    def test_build_input_links_are_rejected(self):
        source = self.write("build.py")
        try:
            (self.tools / "lib").symlink_to(self.tools, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Symbolic links are unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "Links"):
            sdk_recipe.recipe_hash(self.tools)
        (self.tools / "lib").unlink()
        (self.tools / "cmake").mkdir()
        (self.tools / "cmake/linked.cmake").symlink_to(source)
        with self.assertRaisesRegex(ValueError, "Links"):
            sdk_recipe.recipe_hash(self.tools)

    def test_windows_reparse_points_are_rejected_without_link_privileges(self):
        self.write("lib/nested/producer.py")
        self.write("placebo/moltenvk/CMakeLists.txt")
        original_lstat = Path.lstat
        original_iterdir = Path.iterdir
        for relative in (".", "lib", "lib/nested", "lib/nested/producer.py", "placebo", "placebo/moltenvk"):
            with self.subTest(relative=relative):
                def reparse_lstat(path):
                    info = original_lstat(path)
                    if path == self.tools / relative:
                        return SimpleNamespace(st_mode=info.st_mode,
                                               st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
                    return info

                def guarded_iterdir(path):
                    if path == self.tools / relative:
                        self.fail("Build input reparse point was traversed before validation")
                    return original_iterdir(path)

                with patch.object(Path, "lstat", autospec=True, side_effect=reparse_lstat), \
                        patch.object(Path, "iterdir", autospec=True, side_effect=guarded_iterdir), \
                        self.assertRaisesRegex(ValueError, "Links"):
                    sdk_recipe.recipe_hash(self.tools)


if __name__ == "__main__":
    unittest.main()
