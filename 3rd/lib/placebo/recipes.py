"""显式选择静态依赖和平台后端；所有安装前缀都位于 build 内。"""

import os
import shutil
import sys

from ..layout import TOOLS_ROOT, managed
from ..process import run
from .layout import GLSLANG_ARCHIVES
from .sources import source_lock


def cmake_build(name, source, target, prefix, tools, env, jobs, options):
    output = managed(f"out/{target}/placebo/{name}")
    # 刷新配置缓存但保留对象产物，防止切换编译器时 CMake 重置并丢失显式选项。
    args = [tools["cmake"], "--fresh", "-S", source, "-B", output, "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF",
            "-DCMAKE_POSITION_INDEPENDENT_CODE=ON", "-DCMAKE_INSTALL_LIBDIR=lib",
            f"-DCMAKE_INSTALL_PREFIX={prefix.as_posix()}", f"-DCMAKE_C_COMPILER={tools['cc']}",
            f"-DCMAKE_CXX_COMPILER={tools['cxx']}", f"-DCMAKE_MAKE_PROGRAM={tools['ninja']}"]
    if target.startswith("darwin/"):
        args += [f"-DCMAKE_OSX_SYSROOT={tools['sdk']}", "-DCMAKE_OSX_ARCHITECTURES=arm64",
                 "-DCMAKE_OSX_DEPLOYMENT_TARGET=12.0", f"-DCMAKE_OBJC_COMPILER={tools['cc']}",
                 f"-DCMAKE_OBJCXX_COMPILER={tools['cxx']}"]
    run([*args, *options], f"placebo-{name}-configure", env)
    run([tools["cmake"], "--build", output, "--parallel", str(jobs)], f"placebo-{name}-build", env)
    run([tools["cmake"], "--install", output], f"placebo-{name}-install", env)


def build_dependencies(target, prefix, tools, env, jobs):
    cmake_build("glslang", managed("sources/glslang"), target, prefix, tools, env, jobs, [
        "-DBUILD_EXTERNAL=OFF", "-DENABLE_OPT=OFF", "-DENABLE_HLSL=OFF", "-DENABLE_PCH=OFF",
        "-DENABLE_GLSLANG_BINARIES=OFF", "-DGLSLANG_TESTS=OFF", "-DGLSLANG_ENABLE_INSTALL=ON"])
    if target != "linux/amd64":
        windows = target.startswith("windows/")
        cmake_build("spirv-cross", managed("sources/spirv-cross"), target, prefix, tools, env, jobs, [
            "-DSPIRV_CROSS_SHARED=OFF", "-DSPIRV_CROSS_STATIC=ON", "-DSPIRV_CROSS_CLI=OFF",
            "-DSPIRV_CROSS_ENABLE_TESTS=OFF", "-DSPIRV_CROSS_ENABLE_GLSL=ON",
            f"-DSPIRV_CROSS_ENABLE_HLSL={'ON' if windows else 'OFF'}",
            f"-DSPIRV_CROSS_ENABLE_MSL={'OFF' if windows else 'ON'}",
            f"-DSPIRV_CROSS_ENABLE_C_API={'ON' if windows else 'OFF'}",
            "-DSPIRV_CROSS_ENABLE_CPP=OFF", f"-DSPIRV_CROSS_ENABLE_REFLECT={'OFF' if windows else 'ON'}",
            "-DSPIRV_CROSS_ENABLE_UTIL=OFF", "-DSPIRV_CROSS_FORCE_PIC=ON"])
    if target == "darwin/arm64":
        cmake_build("moltenvk", TOOLS_ROOT / "placebo/moltenvk", target, prefix, tools, env, jobs, [
            f"-DTERMOUS_SOURCE_ROOT={managed('sources').as_posix()}",
            f"-DTERMOUS_MOLTENVK_REVISION={source_lock()['moltenvk']['revision']}"])


def overlay_sources():
    source = managed("sources/libplacebo")
    overlay = managed("compat/placebo/libplacebo")
    if overlay.exists():
        shutil.rmtree(overlay)
    shutil.copytree(source, overlay, ignore=shutil.ignore_patterns(".git"))
    path = overlay / "src/d3d11/meson.build"
    text = path.read_text(encoding="utf-8")
    original = "dependency('spirv-cross-c-shared', version: '>=0.29.0', required: d3d11)"
    if text.count(original) != 1:
        raise ValueError("Pinned libplacebo D3D11 dependency declaration changed")
    path.write_text(text.replace(original,
                    "dependency('spirv-cross-c', version: '>=0.29.0', static: true, required: d3d11)"),
                    encoding="utf-8")
    path = overlay / "src/glsl/meson.build"
    text = path.read_text(encoding="utf-8")
    start = "elif not glslang_req.disabled()\n"
    end = "\nendif\n\ncomponents.set('glslang', glslang.found())"
    if text.count(start) != 1 or text.count(end) != 1 or text.index(start) >= text.index(end):
        raise ValueError("Pinned libplacebo glslang dependency declaration changed")
    before, body = text.split(start)
    _, after = body.split(end)
    # find_library 的静态查找不会使用 cpp_link_args 的 -L，且可能混入系统同名库。
    # 固定版本只需要这三份归档；直接传入路径，不探测旧版或可选的系统依赖。
    path.write_text(before + start + "\n  glslang = declare_dependency(\n"
                    "    link_args: meson.get_external_property('termous_glslang_libraries'),\n"
                    "  )\n" + end + after, encoding="utf-8")
    return overlay


def meson_build(target, prefix, tools, env, jobs):
    libraries = [prefix / "lib" / name for name in GLSLANG_ARCHIVES]
    for path in [*libraries, prefix / "include/glslang/build_info.h"]:
        if not path.is_file():
            raise ValueError(f"Pinned glslang installation is incomplete: {path}")
    source = overlay_sources()
    output = managed(f"out/{target}/placebo/libplacebo")
    config = managed(f"out/{target}/placebo/native.ini")
    config.parent.mkdir(parents=True, exist_ok=True)
    flags = ["-I" + (prefix / "include").as_posix(),
             "-I" + managed("sources/fast-float/include").as_posix()]
    link = ["-L" + (prefix / "lib").as_posix()]
    if target != "windows/amd64":
        flags.append("-I" + managed("sources/vulkan-headers/include").as_posix())
    if target == "darwin/arm64":
        flags += ["-mmacosx-version-min=12.0", "-isysroot", tools["sdk"]]
        link += ["-mmacosx-version-min=12.0", "-isysroot", tools["sdk"]]
    # 使用 Meson 自己的字符串语法，路径统一为正斜杠，不交给 shell 解释。
    def literal(value):
        if any(c in str(value) for c in "'\n\r"):
            raise ValueError("Unsupported quote or newline in build tool path")
        return "'" + str(value).replace("\\", "/") + "'"

    def array(values):
        return "[" + ", ".join(literal(value) for value in values) + "]"

    config.write_text("[binaries]\n" + "\n".join(
        f"{key} = {literal(value)}" for key, value in
        (("c", tools["cc"]), ("cpp", tools["cxx"]), ("python", sys.executable), ("pkg-config", tools["pkgconfig"])))
        + "\n[built-in options]\n" + "\n".join(f"{key} = {array(value)}" for key, value in
          (("c_args", flags), ("cpp_args", flags), ("c_link_args", link), ("cpp_link_args", link)))
        + "\n[properties]\ntermous_glslang_libraries = " + array(libraries) + "\n",
        encoding="utf-8")
    build_env = env.copy()
    build_env["PYTHONPATH"] = os.pathsep.join(str(managed(f"sources/{name}/src"))
                                            for name in ("jinja", "markupsafe"))
    build_env["PKG_CONFIG_PATH"] = str(prefix / "lib/pkgconfig")
    build_env["PKG_CONFIG_LIBDIR"] = str(prefix / "lib/pkgconfig")
    # 源码覆盖层没有 Git 元数据，禁止版本脚本意外读取外层 termous-video 仓库。
    build_env["GIT_CEILING_DIRECTORIES"] = str(source.parent)
    command = [tools["meson"], "setup", output, source, "--native-file", config,
               "--prefix", prefix, "--libdir", "lib", "--buildtype=release", "--wrap-mode=nodownload",
               "-Ddefault_library=static", "-Dprefer_static=true", "-Dauto_features=disabled",
               "-Dglslang=enabled", "-Dshaderc=disabled", "-Dopengl=disabled", "-Dvk-proc-addr=disabled",
               "-Dtests=false", "-Ddemos=false", "-Dbench=false", "-Dfuzz=false",
               "-Dlcms=disabled", "-Ddovi=disabled", "-Dlibdovi=disabled", "-Dxxhash=disabled",
               "-Dunwind=disabled", f"-Dd3d11={'enabled' if target == 'windows/amd64' else 'disabled'}",
               f"-Dvulkan={'disabled' if target == 'windows/amd64' else 'enabled'}"]
    if target != "windows/amd64":
        command.append(f"-Dvulkan-registry={managed('sources/vulkan-headers/registry/vk.xml')}")
    if (output / "meson-private/coredata.dat").exists():
        # reconfigure 不重载原生机器文件中的编译器；重新配置时必须读取当前工具链。
        command.append("--wipe")
    run(command, "placebo-configure", build_env)
    run([tools["meson"], "compile", "-C", output, "-j", str(jobs)], "placebo-build", build_env)
    run([tools["meson"], "install", "-C", output, "--no-rebuild"], "placebo-install", build_env)
    if target == "windows/amd64":
        # 这是系统 UCRT 数学函数的导入归档，不是需要分发的 DLL。
        shutil.copyfile(output / "src/ucrt_math.lib", prefix / "lib/libplacebo_ucrt_math.a")
