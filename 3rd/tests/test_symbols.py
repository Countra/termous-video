"""验证符号映射不重写系统引用，且失败时不移除原归档。"""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import symbols
from lib.layout import BUILD_ROOT


class SymbolTests(unittest.TestCase):
    def test_failed_audit_preserves_original_archives(self):
        parent = BUILD_ROOT / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            sdk = Path(temporary)
            (sdk / "lib").mkdir()
            (sdk / "include").mkdir()
            for name in symbols.ARCHIVES:
                (sdk / "lib" / name).write_bytes(b"original archive")
            with patch.object(symbols, "symbol_tools", return_value={"nm": "nm", "objcopy": "objcopy"}), \
                    patch.object(symbols, "read_symbols", return_value={"ARGBToI420"}), \
                    patch.object(symbols, "run"):
                with self.assertRaisesRegex(ValueError, "Incomplete symbol isolation"):
                    symbols.isolate(sdk, "linux/amd64", {})
            for name in symbols.ARCHIVES:
                self.assertEqual((sdk / "lib" / name).read_bytes(), b"original archive")

    def test_platform_decoration(self):
        self.assertEqual(symbols.private_name("_WelsCreateDecoder", "darwin/arm64"), "_termous_video_WelsCreateDecoder")
        self.assertEqual(symbols.private_name("__ZN4Wels", "darwin/arm64"), "_termous_video__ZN4Wels")
        self.assertEqual(symbols.private_name("WelsCreateDecoder", "windows/amd64"), "termous_video_WelsCreateDecoder")

    def test_complete_map_and_external_runtime_reference(self):
        parent = BUILD_ROOT / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            sdk = Path(temporary)
            (sdk / "lib").mkdir()
            (sdk / "include").mkdir()
            for name in symbols.ARCHIVES:
                (sdk / "lib" / name).write_bytes(b"archive")
            definitions = {"libopenh264.a": {"WelsCreateDecoder", "_ZN4Wels", ".refptr.WelsCreateDecoder"},
                           "libyuv.a": {"ARGBToI420"}}

            def read(path, tools, env, *, defined):
                if not defined:
                    return {"malloc", "memcpy"}
                if path.name in definitions:
                    return definitions[path.name]
                name = next(k for k, v in symbols.ARCHIVES.items() if v == path.name)
                return {symbols.PREFIX + s for s in definitions[name]}

            def run(command, *args):
                Path(command[-1]).write_bytes(b"private archive")

            with patch.object(symbols, "symbol_tools", return_value={"nm": "nm", "objcopy": "objcopy"}), \
                    patch.object(symbols, "read_symbols", side_effect=read), \
                    patch.object(symbols, "normalize_archive", return_value=0), \
                    patch.object(symbols, "run", side_effect=run), patch.object(symbols, "capture", return_value="LLVM 18"):
                record = symbols.isolate(sdk, "windows/amd64", {})
            self.assertEqual(record["symbols"], 4)
            mapping = (sdk / "symbols/rename.map").read_text()
            self.assertNotIn("malloc", mapping)
            header = (sdk / "include" / symbols.HEADER).read_text(encoding="utf-8")
            self.assertIn("#define ARGBToI420 termous_video_ARGBToI420", header)
            self.assertNotIn("#define _ZN", header)
            self.assertTrue(all((sdk / "lib" / n).is_file() for n in symbols.ARCHIVES.values()))
            self.assertTrue(all(not (sdk / "lib" / n).exists() for n in symbols.ARCHIVES))


if __name__ == "__main__":
    unittest.main()
