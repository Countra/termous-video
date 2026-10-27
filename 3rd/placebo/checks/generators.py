"""在禁用系统包的解释器中验证固定模板依赖及其实际加载位置。"""

import importlib
from pathlib import Path
import sys


def main():
    if not sys.flags.no_site:
        raise RuntimeError("Generator verification requires Python -S")
    root = Path(sys.argv[1]).resolve() / "3rdparty"
    modules = {}
    for name, package in (("jinja", "jinja2"), ("markupsafe", "markupsafe")):
        module = importlib.import_module(package)
        expected = root / name / "src" / package / "__init__.py"
        if Path(module.__file__).resolve() != expected:
            raise RuntimeError(f"Generator module was not loaded from pinned sources: {package}")
        modules[package] = module
        print(f"Pinned generator module verified: {package}: {expected}")
    template = modules["jinja2"].Environment(autoescape=True).from_string("{{ value }}")
    if template.render(value="<Termous & HDR>") != "&lt;Termous &amp; HDR&gt;":
        raise RuntimeError("Pinned Jinja and MarkupSafe template check failed")


if __name__ == "__main__":
    try:
        main()
    except (ImportError, OSError, RuntimeError) as error:
        print(f"Generator verification failed: {error}", file=sys.stderr)
        sys.exit(1)
