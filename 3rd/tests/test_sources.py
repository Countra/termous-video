"""检查固定来源、修改保护和平台降级边界，不访问网络。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import sources
from lib.layout import managed
from lib.platforms import host_target, link_flags, toolchain


class SourceTests(unittest.TestCase):
    def test_openh264_uses_the_previous_official_pinned_source(self):
        self.assertEqual(sources.source_lock()["openh264"], {
            "url": "https://github.com/cisco/openh264.git", "version": "2.6.0",
            "revision": "652bdb7719f30b52b08e506645a7322ff1b2cc6f"})

    def test_source_checks_revision_remote_and_dirty_tree(self):
        item = sources.source_lock()["x264"]
        cases = (("wrong-url", item["revision"], ""),
                 (item["url"], "2" * 40, ""),
                 (item["url"], item["revision"], "?? untracked-header.h"))
        for responses in cases:
            with self.subTest(responses=responses), patch.object(sources, "git_command", return_value=["git"]), \
                    patch.object(sources, "capture", side_effect=responses), self.assertRaises(ValueError):
                sources.verify_source("x264", item, {})

    def test_source_verification_never_downloads(self):
        item = sources.source_lock()["libyuv"]
        with patch.object(sources, "git_command", return_value=["git"]), \
                patch.object(sources, "capture", side_effect=[item["url"], item["revision"], ""]), \
                patch.object(sources, "run") as run:
            sources.verify_source("libyuv", item, {})
            run.assert_not_called()

    def test_build_cache_rejects_escape(self):
        with self.assertRaises(ValueError):
            managed("../sdk")
        with self.assertRaises(ValueError):
            managed(".")

    def test_platform_validation_before_tool_execution(self):
        with self.assertRaisesRegex(ValueError, "Only native builds"):
            toolchain("darwin/amd64", {})
        with patch("lib.platforms.platform.system", return_value="Darwin"), \
                patch("lib.platforms.platform.machine", return_value="arm64"):
            self.assertEqual(host_target(), "darwin/arm64")

    def test_c_link_dependencies_are_explicit(self):
        self.assertIn("-lm", link_flags("linux/amd64"))
        self.assertIn("-static", link_flags("windows/amd64"))
        self.assertIn("-lc++", link_flags("darwin/arm64"))

    def test_source_lock_rejects_malformed_fields(self):
        for value in ([], None, {"schema": 1}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                sources.validate_source_lock(value)
        for field, value in (("revision", None), ("revision", 123), ("version", "2.6.0\n#define BAD")):
            lock = sources.source_lock()
            lock["x264"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                sources.validate_source_lock(lock)


if __name__ == "__main__":
    unittest.main()
