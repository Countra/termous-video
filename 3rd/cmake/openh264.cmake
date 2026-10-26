include("${CMAKE_CURRENT_LIST_DIR}/openh264_sources.cmake")
set(H264_COMMON_INCLUDES
  "${CMAKE_BINARY_DIR}/generated"
  "${H264_ROOT}/codec/api/wels"
  "${H264_ROOT}/codec/common/inc")
set(H264_PROCESSING_INCLUDES
  "${H264_ROOT}/codec/processing/interface"
  "${H264_ROOT}/codec/processing/src/common"
  "${H264_ROOT}/codec/processing/src/adaptivequantization"
  "${H264_ROOT}/codec/processing/src/downsample"
  "${H264_ROOT}/codec/processing/src/scrolldetection"
  "${H264_ROOT}/codec/processing/src/vaacalc")
# 直接生成固定版本头，不调用上游 generate_version.sh。
file(MAKE_DIRECTORY "${CMAKE_BINARY_DIR}/generated")
file(READ "${CMAKE_CURRENT_LIST_DIR}/../build-lock.json" H264_LOCK)
string(JSON H264_VERSION GET "${H264_LOCK}" openh264 version)
string(JSON H264_REVISION GET "${H264_LOCK}" openh264 revision)
file(WRITE "${CMAKE_BINARY_DIR}/generated/version_gen.h"
  "#define VERSION_NUMBER \"${H264_VERSION}-${H264_REVISION}\"\n")
if(TERMOUS_TARGET STREQUAL "darwin/arm64")
  enable_language(ASM)
  set(H264_ASM_SOURCES ${OPENH264_ARM64})
  set(H264_ASM_INCLUDE "${H264_ROOT}/codec/common/arm64")
  set(H264_DEFINES HAVE_NEON_AARCH64)
else()
  if(WIN32)
    set(CMAKE_ASM_NASM_OBJECT_FORMAT win64)
    set(ASM_ABI WIN64)
  else()
    set(CMAKE_ASM_NASM_OBJECT_FORMAT elf64)
    set(ASM_ABI UNIX64)
  endif()
  enable_language(ASM_NASM)
  set(H264_ASM_SOURCES ${OPENH264_X86})
  set(H264_ASM_INCLUDE "${H264_ROOT}/codec/common/x86/")
  set(H264_DEFINES X86_ASM HAVE_AVX2
    "$<$<COMPILE_LANGUAGE:ASM_NASM>:${ASM_ABI}>")
endif()

# 编码和解码目录存在同名头文件，必须像上游一样隔离编译单元的搜索路径。
add_library(openh264 STATIC)
foreach(part common encoder decoder processing)
  set(part_sources ${OPENH264_COMMON} ${H264_ASM_SOURCES})
  list(FILTER part_sources INCLUDE REGEX "/codec/${part}/")
  add_library(h264_${part} OBJECT ${part_sources})
  target_include_directories(h264_${part} PRIVATE ${H264_COMMON_INCLUDES} "${H264_ASM_INCLUDE}")
  if(part STREQUAL "encoder" OR part STREQUAL "decoder")
    target_include_directories(h264_${part} PRIVATE
      "${H264_ROOT}/codec/${part}/core/inc" "${H264_ROOT}/codec/${part}/plus/inc")
  endif()
  if(part STREQUAL "encoder" OR part STREQUAL "processing")
    target_include_directories(h264_${part} PRIVATE ${H264_PROCESSING_INCLUDES})
  endif()
  target_compile_definitions(h264_${part} PRIVATE GENERATED_VERSION_HEADER ${H264_DEFINES})
  target_compile_options(h264_${part} PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-fno-strict-aliasing>")
  if(NOT WIN32)
    target_compile_options(h264_${part} PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-fstack-protector-all>")
  endif()
  target_sources(openh264 PRIVATE $<TARGET_OBJECTS:h264_${part}>)
endforeach()
