"""验证 LLVM 显式选择、Xcode PATH 干扰和编译前失败边界。"""

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import build_sdk, symbols
from lib.layout import BUILD_ROOT


class SymbolToolTests(unittest.TestCase):
    def setUp(self):
        parent = BUILD_ROOT / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.brew = self.root / "homebrew/bin"
        self.xcode = self.root / "Xcode Toolchain/bin"
        self.names = {name: f"llvm-{name}" + (".exe" if os.name == "nt" else "")
                      for name in ("nm", "objcopy")}
        for directory in (self.brew, self.xcode):
            directory.mkdir(parents=True)
            for name in self.names.values():
                tool = directory / name
                tool.write_bytes(b"test fixture; never executed")
                tool.chmod(0o755)
        self.expected = {name: str(self.brew / filename) for name, filename in self.names.items()}

    def version(self, command, *_args):
        # 只模拟版本输出，路径搜索使用真实文件，以覆盖平台上的 which 行为。
        if Path(command[0]).parent == self.brew:
            return "llvm tool\nHomebrew LLVM version 21.1.0\nOptimized build."
        return "Apple LLVM version 17.0.0"

    def test_explicit_tools_override_xcode_first_path(self):
        env = {"PATH": os.pathsep.join(map(str, (self.xcode, self.brew))),
               **{"LLVM_" + name.upper(): path for name, path in self.expected.items()}}
        with patch.object(symbols, "capture", side_effect=self.version):
            self.assertEqual(symbols.symbol_tools(env), self.expected)

    def test_old_or_unrecognized_version_keeps_strict_validation(self):
        env = {"PATH": str(self.brew)}
        for version in ("LLVM version 17.0.6", "Apple tool without an LLVM version"):
            with self.subTest(version=version), patch.object(symbols, "capture", return_value=version):
                with self.assertRaisesRegex(ValueError, "LLVM 18 or newer") as failure:
                    symbols.symbol_tools(env)
                self.assertIn(version, str(failure.exception))

    def test_build_preserves_tools_after_compiler_changes_path(self):
        env = {"PATH": os.pathsep.join(map(str, (self.brew, self.xcode)))}

        def compiler(_target, environment):
            environment["PATH"] = str(self.xcode) + os.pathsep + environment["PATH"]
            return {name: name for name in ("cc", "cxx", "cmake", "ninja", "sdk")}

        class SelectionChecked(Exception):
            pass

        def isolate(_sdk, target, selected, environment):
            self.assertEqual(target, "darwin/arm64")
            self.assertEqual({name: Path(path) for name, path in selected.items()},
                             {name: Path(path) for name, path in self.expected.items()})
            # 此时再次按 PATH 选择会命中旧 Xcode 工具；隔离必须复用预检结果。
            with self.assertRaisesRegex(ValueError, "LLVM 18 or newer"):
                symbols.symbol_tools(environment)
            raise SelectionChecked()

        with patch.object(symbols, "capture", side_effect=self.version), \
                patch.object(build_sdk, "verify_sources"), \
                patch.object(build_sdk, "verify_review"), \
                patch.object(build_sdk, "toolchain", side_effect=compiler), \
                patch.object(build_sdk, "source_record", return_value={"source_commit": None, "source_dirty": True}), \
                patch.object(build_sdk, "managed", side_effect=lambda p: self.root / p), \
                patch.object(build_sdk, "run"), \
                patch.object(build_sdk, "isolate", side_effect=isolate), \
                self.assertRaises(SelectionChecked):
            build_sdk.build_sdk("darwin/arm64", 4, env)

    def test_missing_tools_stop_before_compilation(self):
        with patch.object(build_sdk, "verify_sources"), \
                patch.object(build_sdk, "symbol_tools", side_effect=ValueError("Required LLVM tool not found")), \
                patch.object(build_sdk, "toolchain") as compiler, \
                patch.object(build_sdk, "run") as run, \
                self.assertRaisesRegex(ValueError, "Required LLVM tool not found"):
            build_sdk.build_sdk("darwin/arm64", 4, {})
        compiler.assert_not_called()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
