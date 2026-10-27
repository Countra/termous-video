"""核对已审查的上游构建入口；下载、审查与执行互相独立。"""

import hashlib
import json

from ..layout import TOOLS_ROOT, managed
from .sources import dependencies, source_lock, verify_sources

REVIEW = TOOLS_ROOT / "placebo/upstream-review.json"


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def review_digest():
    return digest(REVIEW)


def verify_review(target, env, accepted):
    verify_sources(target, env)
    expected = review_digest()
    if accepted != expected:
        raise ValueError(f"Upstream build scripts require approval; expected review SHA256: {expected}")
    data = json.loads(REVIEW.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("sources") != source_lock():
        raise ValueError("Upstream review does not match the pinned dependency sources")
    for name in dependencies(target):
        for relative, sha in data["files"].get(name, {}).items():
            root = managed(f"sources/{name}")
            path = root / relative
            if not path.resolve().is_relative_to(root.resolve()) or digest(path) != sha:
                raise ValueError(f"Reviewed upstream file changed: {name}/{relative}")
    return expected
