"""用 Go 自身检查三平台 cgo 参数；只生成构建命令，不编译或运行原生代码。"""

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = os.environ | {"GOWORK": "off", "GOTOOLCHAIN": "local"}
    # 跨平台只借用宿主编译器生成命令，避免要求安装交叉编译器。
    compilers = json.loads(subprocess.check_output(["go", "env", "-json", "CC", "CXX"],
                                                   cwd=ROOT, env=env, text=True, encoding="utf-8", timeout=30))
    for category in ("CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS"):
        env[f"CGO_{category}_ALLOW"] = ""
    for target in ("windows/amd64", "linux/amd64", "darwin/arm64"):
        goos, arch = target.split("/")
        target_env = env | compilers | {"GOOS": goos, "GOARCH": arch, "CGO_ENABLED": "1"}
        log = ROOT / "build/logs" / f"cgo-flags-{goos}-{arch}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        # 强制生成所有包的命令，已有构建缓存不能绕过参数检查。
        with log.open("w", encoding="utf-8") as output:
            result = subprocess.run(["go", "build", "-a", "-n", "-tags=video_native_fixture",
                                     "./internal/native", "./internal/colornative"],
                                    cwd=ROOT, env=target_env, stdout=output, stderr=subprocess.STDOUT, timeout=30)
        if result.returncode:
            tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-8:])
            raise RuntimeError(f"Go rejected cgo flags for {target}; log: {log}\n{tail}")
        print(f"cgo flags passed: {target}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"cgo flag checks failed: {error}", file=sys.stderr)
        sys.exit(1)
