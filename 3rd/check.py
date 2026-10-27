"""离线检查 Python 语法、固定来源和本仓库构建配方。"""

import ast
import re
import sys
from pathlib import Path

sys.pycache_prefix = str(Path(__file__).resolve().parent.parent / "build/cache/pycache")

from lib.layout import PROJECT_ROOT, TOOLS_ROOT
from lib.sources import source_lock
from lib.placebo.sources import source_lock as placebo_lock
from lib.placebo.review import REVIEW, review_digest
import json


def main():
    source_lock()
    if json.loads(REVIEW.read_text(encoding="utf-8"))["sources"] != placebo_lock():
        raise ValueError("libplacebo review must match the dependency lock")
    files = sorted([*TOOLS_ROOT.rglob("*.py"), *(PROJECT_ROOT / "scripts").rglob("*.py")])
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    # 配方只编译固定源码，不允许意外引入上游脚本执行或配置时下载。
    for path in [TOOLS_ROOT / "CMakeLists.txt", *sorted((TOOLS_ROOT / "cmake").glob("*.cmake")),
                 *sorted((TOOLS_ROOT / "placebo").rglob("CMakeLists.txt"))]:
        text = path.read_text(encoding="utf-8")
        if re.search(r"\b(execute_process|externalproject_add|fetchcontent_\w+|add_subdirectory)\s*\(", text, re.IGNORECASE):
            raise ValueError(f"Unexpected external build entry in {path.name}")
    workflow = (PROJECT_ROOT / ".github/workflows/build-native-sdk.yml").read_text(encoding="utf-8")
    if re.search(r"[\u4e00-\u9fff]", workflow):
        raise ValueError("SDK workflow must use English text")
    for target in ("windows/amd64", "linux/amd64", "darwin/arm64"):
        if f"target: {target}" not in workflow:
            raise ValueError(f"CI matrix is missing {target}")
    if f'ACCEPTED_PLACEBO_REVIEW: "{review_digest()}"' not in workflow:
        raise ValueError("SDK workflow review digest does not match the approved libplacebo inputs")
    print(f"Static checks passed: {len(files)} Python files and three SDK targets")


if __name__ == "__main__":
    try:
        main()
    except (SyntaxError, ValueError, OSError) as error:
        print(f"Static checks failed: {error}", file=sys.stderr)
        sys.exit(1)
