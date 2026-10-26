"""所有构建副产物限制在本仓库 build 内。"""

from pathlib import Path

TOOLS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS_ROOT.parent
BUILD_ROOT = PROJECT_ROOT / "build"


def managed(relative):
    path = (BUILD_ROOT / relative).resolve()
    if path == BUILD_ROOT.resolve() or not path.is_relative_to(BUILD_ROOT.resolve()):
        raise ValueError(f"Path escapes the build cache: {relative}")
    return path
