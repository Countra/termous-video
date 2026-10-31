"""先验证暂存 SDK，再替换安装目录；失败时恢复旧版本。"""

import json
import shutil
from pathlib import Path

from .layout import BUILD_ROOT, PROJECT_ROOT, managed
from .sdk_manifest import checked_files, verify_manifest


def install_sdk(target, staged):
    staged = Path(staged)
    verify_manifest(staged, target)
    destination = PROJECT_ROOT / "sdk" / target
    backup = managed(f"sdk-backup/{target}")
    sdk_root = PROJECT_ROOT / "sdk"
    if sdk_root.exists() or sdk_root.is_symlink():
        # 首次安装某个平台时也检查父目录，避免通过 SDK 根目录链接写到其他位置。
        checked_files(sdk_root)
    for path, owner in ((staged, BUILD_ROOT), (backup, BUILD_ROOT), (destination, PROJECT_ROOT / "sdk")):
        if path.resolve() == owner.resolve() or not path.resolve().is_relative_to(owner.resolve()):
            raise ValueError(f"Installation path escapes its owner: {path}")
    if backup.exists():
        raise ValueError(f"Previous backup exists; inspect it before retrying: {backup}")
    previous = destination.exists()
    if previous:
        checked_files(destination)
        data = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("platform") != target
                or data.get("scope") != "video_dependencies"):
            raise ValueError("Refusing to replace an unrelated SDK directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if previous:
        destination.replace(backup)
    try:
        staged.replace(destination)
    except OSError:
        if previous:
            backup.replace(destination)
        raise
    if previous:
        shutil.rmtree(backup)
