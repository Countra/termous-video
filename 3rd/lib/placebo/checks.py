"""只用合成像素验证真实 C/cgo 链接，单独记录设备不可用。"""

import json
import shutil
import subprocess

from ..layout import TOOLS_ROOT, managed
from ..process import run
from ..sdk_link import dynamic_dependencies
from ..sdk_manifest import sdk_fingerprint
from .layout import archives, system_flags
from ..symbols import ARCHIVES as CODEC_ARCHIVES

EXTRA_SYSTEM_DLLS = {"version.dll", "shlwapi.dll", "ole32.dll", "gdi32.dll", "d3d11.dll", "dxgi.dll"}


def macos_crash_backtrace(binary, arguments, env, log):
    # 只重跑合成验证程序，禁用用户 LLDB 初始化文件；诊断结果不改变原失败状态。
    command = ["/usr/bin/xcrun", "lldb", "--no-lldbinit", "--batch",
               "--one-line", "settings set target.disable-aslr false", "--one-line", "run",
               "--one-line-on-crash", "thread backtrace all", "--", str(binary), *arguments]
    try:
        with log.open("w", encoding="utf-8") as stream:
            try:
                result = subprocess.run(command, env=env, cwd=binary.parent, stdout=stream,
                                        stderr=subprocess.STDOUT, timeout=60, check=False)
                stream.write(f"\nLLDB diagnostic exit code: {result.returncode}\n")
            except (OSError, subprocess.TimeoutExpired) as error:
                stream.write(f"\nLLDB diagnostics unavailable: {error}\n")
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-60:])
        return f"\nCrash diagnostics: {log}\n{tail}"
    except OSError as error:
        return f"\nUnable to save crash diagnostics: {error}"


def run_render(binary, label, target, env):
    arguments = ["--software"] if target.startswith("windows/") else []
    log = managed(f"logs/{label}.log")
    log.parent.mkdir(parents=True, exist_ok=True)
    backtrace = log.with_name(log.stem + "-backtrace.log")
    backtrace.unlink(missing_ok=True)
    try:
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run([str(binary), *arguments], env=env, cwd=binary.parent,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=120, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{label} timed out; see {log}") from error
    if result.returncode == 0:
        print(f"[{label}] Synthetic HDR rendering passed; log: {log}")
        return "passed"
    if result.returncode == 77 and target == "darwin/arm64" and env.get("PLACEBO_ALLOW_NO_GPU") == "1":
        print(f"[{label}] GPU unavailable; runtime validation is incomplete; log: {log}")
        return "unavailable"
    tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-30:])
    if target == "darwin/arm64" and result.returncode < 0:
        tail += macos_crash_backtrace(binary, arguments, env, backtrace)
    raise RuntimeError(f"{label} failed ({result.returncode}); log: {log}\n{tail}")


def verify_link(sdk, target, tools, env):
    check = managed(f"checks/placebo/{target}")
    check.mkdir(parents=True, exist_ok=True)
    (check / "result.json").unlink(missing_ok=True)
    source = TOOLS_ROOT / "placebo/checks"
    compile_flags = ["-std=c11", "-O2", "-DPL_STATIC", "-I", str(sdk / "include")]
    if target == "darwin/arm64":
        compile_flags += ["-mmacosx-version-min=12.0", "-g"]
    names = ["main", "device", "render"]
    if target == "darwin/arm64":
        names.append("metal")
    objects = []
    for name in names:
        obj = check / (name + ".o")
        filename = name + (".m" if name == "metal" else ".c")
        run([tools["cc"], *compile_flags, "-c", source / filename, "-o", obj],
            f"placebo-check-{name}", env)
        objects.append(obj)
    libraries = [(sdk / "lib" / name).as_posix() for name in archives(target)]
    flags = system_flags(target)
    whole = ([arg for archive in libraries for arg in ("-Xlinker", "-force_load", "-Xlinker", archive)]
             if target.startswith("darwin/") else ["-Wl,--whole-archive", *libraries, "-Wl,--no-whole-archive"])
    suffix = ".exe" if target.startswith("windows/") else ""
    imports = set()
    for name, libs in (("c", libraries), ("whole", whole)):
        binary = check / (name + suffix)
        run([tools["cc"], *objects, *libs, *flags, "-o", binary], f"placebo-{name}-link", env)
        imports.update(dynamic_dependencies(binary, target, tools, env, allowed_extra=EXTRA_SYSTEM_DLLS))
        run([binary, "--api-only"], f"placebo-{name}-api", env, timeout=30)
    native_status = run_render(check / ("c" + suffix), "placebo-c-render", target, env)
    cgo = check / "cgo"
    cgo.mkdir(exist_ok=True)
    for name in ("check.h", "device.c", "render.c"):
        shutil.copyfile(source / name, cgo / name)
    if target == "darwin/arm64":
        shutil.copyfile(source / "metal.m", cgo / "metal.m")
    shutil.copyfile(source / "cgo.go.in", cgo / "main.go")
    (cgo / "go.mod").write_text("module termous/video/placebocheck\n\ngo 1.24.0\n", encoding="utf-8")
    go_env = env.copy()
    for name, relative in (("GOCACHE", "cache/go/build"), ("GOMODCACHE", "cache/go/mod"),
                           ("GOTMPDIR", "cache/go/tmp")):
        if not go_env.get(name):
            path = managed(relative)
            path.mkdir(parents=True, exist_ok=True)
            go_env[name] = str(path)
    go_env.update(CGO_ENABLED="1", CC=tools["cc"], CXX=tools["cxx"], GOWORK="off", GOTOOLCHAIN="local",
                  GOFLAGS="", GOOS=target.split("/")[0], GOARCH=target.split("/")[1],
                  CGO_CPPFLAGS=f'-DPL_STATIC -DTERMOUS_PLACEBO_SDK_{sdk_fingerprint(sdk)}=1 '
                               f'"-I{(sdk / "include").as_posix()}"',
                  CGO_CFLAGS="-std=c11 -O2" + (" -mmacosx-version-min=12.0" if target.startswith("darwin/") else ""),
                  CGO_LDFLAGS=" ".join([*(f'"{path}"' for path in libraries), *flags]))
    binary = check / ("cgo-link" + suffix)
    run([tools["go"], "build", "-o", binary, "."], "placebo-cgo-link", go_env, cgo)
    imports.update(dynamic_dependencies(binary, target, tools, env, allowed_extra=EXTRA_SYSTEM_DLLS))
    run([binary, "--api-only"], "placebo-cgo-api", env, timeout=30)
    cgo_status = run_render(binary, "placebo-cgo-render", target, env)
    if native_status != cgo_status:
        raise RuntimeError("C and cgo GPU runtime results disagree")
    report = {"c_link": True, "whole_archive_link": True, "cgo_link": True, "api_smoke": True,
              "hdr_render": native_status, "desktop_captured": False, "system_dependencies": sorted(imports)}
    (check / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def verify_codec_link(codec_sdk, component, target, tools, env):
    check = managed(f"checks/placebo/{target}")
    libraries = [(component / "lib" / name).as_posix() for name in archives(target)]
    libraries += [(codec_sdk / "lib" / name).as_posix() for name in CODEC_ARCHIVES.values()]
    whole = ([arg for archive in libraries for arg in ("-Xlinker", "-force_load", "-Xlinker", archive)]
             if target.startswith("darwin/") else ["-Wl,--whole-archive", *libraries, "-Wl,--no-whole-archive"])
    binary = check / ("codec-coexist.exe" if target.startswith("windows/") else "codec-coexist")
    names = ["main", "device", "render"]
    if target == "darwin/arm64":
        names.append("metal")
    # 全归档强制纳入两组依赖，避免按需抽取掩盖同名强符号冲突。
    run([tools["cc"], *(check / (name + ".o") for name in names),
         *whole, *system_flags(target), "-o", binary], "placebo-codec-coexist-link", env)
    dynamic_dependencies(binary, target, tools, env, allowed_extra=EXTRA_SYSTEM_DLLS)
    run([binary, "--api-only"], "placebo-codec-coexist-run", env, timeout=30)
