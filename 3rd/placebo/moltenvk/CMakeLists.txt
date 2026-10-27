cmake_minimum_required(VERSION 3.24)
project(termous_placebo_moltenvk VERSION 1.4.2 LANGUAGES C CXX OBJC OBJCXX)

if(NOT APPLE OR CMAKE_CROSSCOMPILING OR NOT CMAKE_OSX_ARCHITECTURES STREQUAL "arm64")
  message(FATAL_ERROR "MoltenVK requires a native Apple Silicon build")
endif()
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OBJCXX_STANDARD 17)
set(CMAKE_OBJCXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(MVK_ROOT "${TERMOUS_SOURCE_ROOT}/moltenvk")

# 固定提交的源文件集合沿用上游 CMake 组织；不执行 CPM 下载或打包脚本。
file(GLOB_RECURSE MVK_COMMON "${MVK_ROOT}/Common/*.c" "${MVK_ROOT}/Common/*.cpp"
     "${MVK_ROOT}/Common/*.m" "${MVK_ROOT}/Common/*.mm")
file(GLOB_RECURSE MVK_CONVERTER "${MVK_ROOT}/MoltenVKShaderConverter/MoltenVKShaderConverter/*.cpp"
     "${MVK_ROOT}/MoltenVKShaderConverter/MoltenVKShaderConverter/*.c"
     "${MVK_ROOT}/MoltenVKShaderConverter/MoltenVKShaderConverter/*.m"
     "${MVK_ROOT}/MoltenVKShaderConverter/MoltenVKShaderConverter/*.mm")
file(GLOB_RECURSE MVK_DRIVER "${MVK_ROOT}/MoltenVK/MoltenVK/*.c" "${MVK_ROOT}/MoltenVK/MoltenVK/*.cpp"
     "${MVK_ROOT}/MoltenVK/MoltenVK/*.m" "${MVK_ROOT}/MoltenVK/MoltenVK/*.mm")
add_library(MoltenVK_Common STATIC ${MVK_COMMON})
add_library(MoltenVK_ShaderConverter STATIC ${MVK_CONVERTER})
add_library(MoltenVK STATIC ${MVK_DRIVER})
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/mvkGitRevDerived.h"
     "// 固定来源提交，避免把外层仓库版本写入驱动。\nstatic const char* mvkRevString = \"${TERMOUS_MOLTENVK_REVISION}\";\n")

foreach(target MoltenVK_Common MoltenVK_ShaderConverter MoltenVK)
  target_compile_definitions(${target} PRIVATE MVK_CONFIG_LOG_LEVEL=2 MVK_USE_METAL_PRIVATE_API=0
                            MVK_EXCLUDE_SPIRV_TOOLS=1 MVK_FRAMEWORK_VERSION=1.4.2)
  target_compile_options(${target} PRIVATE -Wno-deprecated-declarations -Wno-vla-cxx-extension)
  target_include_directories(${target} PRIVATE
    "${MVK_ROOT}/Common" "${MVK_ROOT}/MoltenVK/include"
    "${MVK_ROOT}/MoltenVKShaderConverter" "${TERMOUS_SOURCE_ROOT}/spirv-cross"
    "${TERMOUS_SOURCE_ROOT}/vulkan-headers/include" "${TERMOUS_SOURCE_ROOT}/cereal/include"
    "${CMAKE_CURRENT_BINARY_DIR}")
endforeach()
foreach(section API Commands GPUObjects Layers OS Utility Vulkan)
  target_include_directories(MoltenVK PRIVATE "${MVK_ROOT}/MoltenVK/MoltenVK/${section}")
endforeach()
# SPIRV-Tools 仅用于反汇编调试文本；保留实际 SPIR-V→MSL 和 cereal 管线缓存。
install(TARGETS MoltenVK MoltenVK_ShaderConverter MoltenVK_Common ARCHIVE DESTINATION lib)
