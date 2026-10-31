"""验证旧 SDK 的待重建状态不掩盖损坏、缺平台或混合代次。"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_sdk import TOOLS, TARGETS, fixture, sdk_entry, sdk_manifest


def previous_fixture(directory, target, generation):
    fixture(directory, target)
    path = directory / "manifest.json"
    data = json.loads(path.read_text())
    data["schema"] = generation
    removed = "x264" if generation == 2 else "openh264"
    del data["sources"][removed]
    data["sources"]["schema"] = 1 if generation == 2 else 2
    (directory / f"lib/libtermous_video_{removed}.a").unlink()
    if removed == "x264":
        for name in ("include/x264.h", "include/x264_config.h", "licenses/x264-COPYING"):
            (directory / name).unlink()
    else:
        shutil.rmtree(directory / "include/wels")
        (directory / "licenses/OpenH264-LICENSE").unlink()
    (directory / "build-lock.json").write_text(json.dumps(data["sources"]))
    data["files"] = sdk_manifest.inventory(directory)
    path.write_text(json.dumps(data))


class GenerationTests(unittest.TestCase):
    def setUp(self):
        parent = TOOLS.parent / "build/tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        change = patch.object(sdk_entry, "PROJECT_ROOT", self.root)
        change.start()
        self.addCleanup(change.stop)

    def previous_set(self, generation):
        for target in TARGETS:
            previous_fixture(self.root / "sdk" / target, target, generation)

    def test_complete_previous_generations_require_rebuild(self):
        for generation in (2, 3):
            with self.subTest(generation=generation):
                self.previous_set(generation)
                self.assertFalse(sdk_entry.audit_installed(allow_unbuilt=True))
                with self.assertRaisesRegex(ValueError, "build format mismatch"):
                    sdk_entry.audit_installed()

    def test_old_and_new_or_different_old_generations_cannot_be_mixed(self):
        for generation in (2, 4):
            with self.subTest(generation=generation):
                self.previous_set(3)
                directory = self.root / "sdk" / TARGETS[0]
                if generation == 4:
                    fixture(directory, TARGETS[0])
                else:
                    previous_fixture(directory, TARGETS[0], generation)
                with self.assertRaises(ValueError):
                    sdk_entry.audit_installed(allow_unbuilt=True)

    def test_old_artifact_tampering_is_not_skipped(self):
        self.previous_set(3)
        (self.root / "sdk" / TARGETS[0] / "lib/libtermous_video_x264.a").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "digest"):
            sdk_entry.audit_installed(allow_unbuilt=True)

    def test_old_headers_and_licenses_are_required_even_with_updated_inventory(self):
        for generation, name in ((2, "include/wels/codec_def.h"), (3, "licenses/x264-COPYING")):
            with self.subTest(generation=generation):
                self.previous_set(generation)
                directory = self.root / "sdk" / TARGETS[0]
                (directory / name).unlink()
                path = directory / "manifest.json"
                data = json.loads(path.read_text())
                data["files"] = sdk_manifest.inventory(directory)
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, "required payload"):
                    sdk_entry.audit_installed(allow_unbuilt=True)

    def test_old_lock_must_match_declared_dependencies(self):
        self.previous_set(3)
        directory = self.root / "sdk" / TARGETS[0]
        (directory / "build-lock.json").write_text("{}")
        path = directory / "manifest.json"
        data = json.loads(path.read_text())
        data["files"] = sdk_manifest.inventory(directory)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "dependency lock"):
            sdk_entry.audit_installed(allow_unbuilt=True)

    def test_old_set_rejects_mixed_or_invalid_archives_with_updated_inventory(self):
        for name, content in (("lib/libtermous_video_openh264.a", b"!<arch>\n"),
                              ("lib/libtermous_video_x264.a", b"!<thin>\n"),
                              ("lib/libtermous_video_yuv.a", b"broken")):
            with self.subTest(name=name):
                self.previous_set(3)
                directory = self.root / "sdk" / TARGETS[0]
                (directory / name).write_bytes(content)
                path = directory / "manifest.json"
                data = json.loads(path.read_text())
                data["files"] = sdk_manifest.inventory(directory)
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, "archive"):
                    sdk_entry.audit_installed(allow_unbuilt=True)

    def test_old_set_validates_the_placebo_component(self):
        for mutation in ("archive", "verification"):
            with self.subTest(mutation=mutation):
                self.previous_set(3)
                directory = self.root / "sdk" / TARGETS[0]
                component = directory / "placebo"
                path = component / "manifest.json"
                data = json.loads(path.read_text())
                if mutation == "archive":
                    next((component / "lib").glob("*.a")).unlink()
                    data["files"] = sdk_manifest.inventory(component)
                else:
                    data["verification"]["c_link"] = False
                path.write_text(json.dumps(data))
                path = directory / "manifest.json"
                data = json.loads(path.read_text())
                data["files"] = sdk_manifest.inventory(directory)
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, "libplacebo SDK"):
                    sdk_entry.audit_installed(allow_unbuilt=True)

    def test_missing_old_platform_is_not_skipped(self):
        self.previous_set(3)
        shutil.rmtree(self.root / "sdk" / TARGETS[1])
        with self.assertRaises(OSError):
            sdk_entry.audit_installed(allow_unbuilt=True)

    def test_old_generations_require_consistent_provenance(self):
        self.previous_set(3)
        path = self.root / "sdk" / TARGETS[1] / "manifest.json"
        data = json.loads(path.read_text())
        data["source_commit"] = "2" * 40
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "same source"):
            sdk_entry.audit_installed(allow_unbuilt=True)

    def test_malformed_generation_reports_validation_error(self):
        self.previous_set(3)
        path = self.root / "sdk" / TARGETS[0] / "manifest.json"
        data = json.loads(path.read_text())
        data["schema"] = []
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            sdk_entry.audit_installed(allow_unbuilt=True)


if __name__ == "__main__":
    unittest.main()
