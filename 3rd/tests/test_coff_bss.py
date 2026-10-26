"""COFF 归档修复只改变未初始化数据段的文件偏移，不改变载荷布局。"""

from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.coff_bss import normalize_archive
from lib.layout import BUILD_ROOT
from lib.sdk_link import dynamic_dependencies


class COFFBSSTests(unittest.TestCase):
    def test_executable_check_rejects_materialized_bss(self):
        for pointer in ("00000000", "00120000"):
            sections = f"  6 .bss 0206eb78 000000014148f000 000000014148f000 {pointer} 2**4"
            with patch("lib.sdk_link.capture", side_effect=["DLL Name: KERNEL32.dll", sections]):
                if pointer == "00000000":
                    self.assertEqual(dynamic_dependencies("fixture.exe", "windows/amd64", {"inspect": "objdump"}, {}), ["KERNEL32.dll"])
                else:
                    with self.assertRaisesRegex(RuntimeError, "BSS"):
                        dynamic_dependencies("fixture.exe", "windows/amd64", {"inspect": "objdump"}, {})

    def fixture(self):
        parent = BUILD_ROOT / "tests"
        parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(temporary.cleanup)
        obj = bytearray(116)
        struct.pack_into("<HH", obj, 0, 0x8664, 2)
        obj[20:24] = b".bss"
        obj[60:65] = b".data"
        for section, flags in ((20, 0xc0300080), (60, 0xc0300040)):
            struct.pack_into("<II", obj, section + 16, 16, 100)
            struct.pack_into("<I", obj, section + 36, flags)
        header = f"{'fixture.o/':<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{len(obj):<10}`\n".encode()
        path = Path(temporary.name) / "fixture.a"
        path.write_bytes(b"!<arch>\n" + header + obj)
        return path

    def test_zeroes_only_bss_pointer_and_is_idempotent(self):
        path = self.fixture()
        expected = bytearray(path.read_bytes())
        struct.pack_into("<I", expected, 68 + 20 + 20, 0)
        self.assertEqual(normalize_archive(path), 1)
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(normalize_archive(path), 0)

    def test_malformed_table_does_not_write_partial_changes(self):
        path = self.fixture()
        damaged = bytearray(path.read_bytes())
        struct.pack_into("<H", damaged, 68 + 2, 100)
        path.write_bytes(damaged)
        with self.assertRaisesRegex(ValueError, "section table"):
            normalize_archive(path)
        self.assertEqual(path.read_bytes(), damaged)
