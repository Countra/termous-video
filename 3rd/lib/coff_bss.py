"""保持 COFF 未初始化数据段的零文件偏移，避免 GNU 链接器把整个 BSS 写进 EXE。"""

import struct
from pathlib import Path


def normalize_archive(path):
    path = Path(path)
    data = bytearray(path.read_bytes())
    if data[:8] != b"!<arch>\n":
        raise ValueError("Expected a regular COFF archive")
    offset, changed = 8, 0
    while offset < len(data):
        if offset + 60 > len(data) or data[offset + 58:offset + 60] != b"`\n":
            raise ValueError("Invalid COFF archive member header")
        name = bytes(data[offset:offset + 16]).strip()
        size = int(data[offset + 48:offset + 58])
        start, end = offset + 60, offset + 60 + size
        if size < 0 or end > len(data):
            raise ValueError("Invalid COFF archive member size")
        if name not in (b"/", b"//", b"/SYM64/"):
            changed += normalize_object(data, start, end)
        offset = end + size % 2
    if offset != len(data):
        raise ValueError("Invalid COFF archive alignment")
    if changed:
        path.write_bytes(data)
    return changed


def normalize_object(data, start, end):
    if end - start < 20 or struct.unpack_from("<H", data, start)[0] != 0x8664:
        raise ValueError("Expected an AMD64 COFF object")
    sections = struct.unpack_from("<H", data, start + 2)[0]
    optional = struct.unpack_from("<H", data, start + 16)[0]
    table = start + 20 + optional
    if optional or table + sections * 40 > end:
        raise ValueError("Invalid COFF object section table")
    changed = 0
    for index in range(sections):
        section = table + index * 40
        flags = struct.unpack_from("<I", data, section + 36)[0]
        if not flags & 0x80:
            continue
        # IMAGE_SCN_CNT_UNINITIALIZED_DATA 没有文件载荷。某些 LLVM 版本改写后
        # 留下非零 PointerToRawData，GNU ld 因此把包含 Go 全局变量的 BSS 落盘。
        # 只归零该字段，保留段大小、符号、归档索引和所有成员偏移。
        if flags & 0x60 or struct.unpack_from("<H", data, section + 32)[0]:
            raise ValueError("Unexpected initialized data or relocations in COFF BSS")
        if struct.unpack_from("<I", data, section + 20)[0]:
            struct.pack_into("<I", data, section + 20, 0)
            changed += 1
    return changed
