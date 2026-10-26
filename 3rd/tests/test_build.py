"""验证构建来源变化、超时和失败时不安装产物。"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import build_sdk, process
from lib.layout import BUILD_ROOT


class BuildTests(unittest.TestCase):
    def setUp(self):
        parent = BUILD_ROOT / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_dirty_recipe_change_during_build_stops_install(self):
        tools = {key: key for key in ("cmake", "ninja", "cc", "cxx", "nasm")}
        changes = (
            patch.object(build_sdk, "managed", side_effect=lambda p: self.root / p),
            patch.object(build_sdk, "verify_sources"),
            patch.object(build_sdk, "toolchain", return_value=tools),
            patch.object(build_sdk, "source_record", return_value={"source_commit": None, "source_dirty": True}),
            patch.object(build_sdk, "recipe_hash", side_effect=["1" * 64, "2" * 64]),
            patch.object(build_sdk, "run"),
            patch.object(build_sdk.shutil, "copyfile"),
            patch.object(build_sdk, "verify_link", return_value={}),
            patch.object(build_sdk, "isolate", return_value={}),
        )
        for change in changes:
            change.start()
            self.addCleanup(change.stop)
        with patch.object(build_sdk, "install_sdk") as install:
            with self.assertRaisesRegex(ValueError, "recipe changed"):
                build_sdk.build_sdk("windows/amd64", 4, {})
            install.assert_not_called()

    def test_publication_rejects_dirty_sources_before_compile(self):
        with patch.object(build_sdk, "verify_sources"), patch.object(build_sdk, "toolchain"), \
                patch.object(build_sdk, "source_record", return_value={"source_commit": "1" * 40, "source_dirty": True}), \
                patch.object(build_sdk, "run") as run, \
                self.assertRaisesRegex(ValueError, "clean working tree"):
            build_sdk.build_sdk("windows/amd64", 4, {"SOURCE_COMMIT": "1" * 40})
        run.assert_not_called()

    def test_native_timeout_is_reported_with_log_path(self):
        with patch.object(process, "managed", side_effect=lambda p: self.root / p), \
                patch.object(process.subprocess, "run", side_effect=subprocess.TimeoutExpired("smoke", 30)) as run, \
                self.assertRaisesRegex(RuntimeError, "smoke timed out after 30 seconds"):
            process.run(["smoke"], "smoke", {}, timeout=30)
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        self.assertTrue((self.root / "logs/smoke.log").is_file())

    def test_tool_probe_timeout_is_reported(self):
        with patch.object(process.subprocess, "run", side_effect=subprocess.TimeoutExpired("gcc", 60)), \
                self.assertRaisesRegex(RuntimeError, "timed out after 60 seconds"):
            process.capture(["gcc", "--version"], self.root, {})


if __name__ == "__main__":
    unittest.main()
