"""统一子进程环境与日志，不改写宿主环境。"""

import os
import subprocess

from .layout import BUILD_ROOT, managed


def environment():
    env = os.environ.copy()
    for name, relative in {
        "TEMP": "cache/tmp", "TMP": "cache/tmp", "TMPDIR": "cache/tmp",
        "XDG_CACHE_HOME": "cache/xdg", "PYTHONPYCACHEPREFIX": "cache/pycache",
    }.items():
        directory = managed(relative)
        directory.mkdir(parents=True, exist_ok=True)
        env[name] = str(directory)
    env.update(PYTHONUTF8="1", PYTHONNOUSERSITE="1", GIT_TERMINAL_PROMPT="0")
    return env


def capture(command, cwd, env, input_text=None):
    try:
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=env, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", input=input_text,
                                timeout=60, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Command timed out after 60 seconds: {command[0]}") from error
    if result.returncode:
        raise RuntimeError(f"Command failed: {subprocess.list2cmdline(list(map(str, command)))}\n"
                           f"{result.stderr[-3000:]}")
    return result.stdout.strip()


def run(command, label, env, cwd=None, *, timeout=1800):
    command = list(map(str, command))
    log = managed(f"logs/{label}.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    print(f"[{label}] {subprocess.list2cmdline(command)}\nLog: {log}", flush=True)
    with log.open("w", encoding="utf-8") as stream:
        try:
            result = subprocess.run(command, cwd=cwd or BUILD_ROOT, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"{label} timed out after {timeout} seconds; see {log}") from error
    if result.returncode:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-24:])
        raise RuntimeError(f"{label} failed with exit code {result.returncode}\n{tail}")
    print(f"[{label}] Completed", flush=True)
