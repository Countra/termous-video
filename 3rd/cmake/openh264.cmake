include("${CMAKE_CURRENT_LIST_DIR}/openh264_sources.cmake")
set(OPENH264_CONFIG_DIR "${CMAKE_CURRENT_BINARY_DIR}/openh264-config")
set(OPENH264_COMMON_INCLUDES
  "${OPENH264_CONFIG_DIR}"
  "${OPENH264_ROOT}/codec/api/wels"
  "${OPENH264_ROOT}/codec/common/inc")
set(OPENH264_PROCESSING_INCLUDES
  "${OPENH264_ROOT}/codec/processing/interface"
  "${OPENH264_ROOT}/codec/processing/src/common"
  "${OPENH264_ROOT}/codec/processing/src/adaptivequantization"
  "${OPENH264_ROOT}/codec/processing/src/downsample"
  "${OPENH264_ROOT}/codec/processing/src/scrolldetection"
  "${OPENH264_ROOT}/codec/processing/src/vaacalc")
# 直接生成固定版本头，不调用上游 generate_version.sh。
file(MAKE_DIRECTORY "${OPENH264_CONFIG_DIR}")
file(READ "${CMAKE_CURRENT_LIST_DIR}/../build-lock.json" OPENH264_LOCK)
string(JSON OPENH264_VERSION GET "${OPENH264_LOCK}" openh264 version)
string(JSON OPENH264_REVISION GET "${OPENH264_LOCK}" openh264 revision)
file(CONFIGURE OUTPUT "${OPENH264_CONFIG_DIR}/version_gen.h" CONTENT
  "#define VERSION_NUMBER \"${OPENH264_VERSION}-${OPENH264_REVISION}\"\n")
if(TERMOUS_TARGET STREQUAL "darwin/arm64")
  enable_language(ASM)
  set(OPENH264_ASM_SOURCES ${OPENH264_ARM64})
  set(OPENH264_ASM_INCLUDE "${OPENH264_ROOT}/codec/common/arm64")
  set(OPENH264_DEFINES HAVE_NEON_AARCH64)
else()
  if(WIN32)
    set(CMAKE_ASM_NASM_OBJECT_FORMAT win64)
    set(OPENH264_ASM_ABI WIN64)
  else()
    set(CMAKE_ASM_NASM_OBJECT_FORMAT elf64)
    set(OPENH264_ASM_ABI UNIX64)
  endif()
  enable_language(ASM_NASM)
  set(OPENH264_ASM_SOURCES ${OPENH264_X86})
  set(OPENH264_ASM_INCLUDE "${OPENH264_ROOT}/codec/common/x86/")
  set(OPENH264_DEFINES X86_ASM HAVE_AVX2
    "$<$<COMPILE_LANGUAGE:ASM_NASM>:${OPENH264_ASM_ABI}>")
endif()

# 编码和解码目录存在同名头文件，必须像上游一样隔离编译单元的搜索路径。
add_library(openh264 STATIC)
foreach(part common encoder decoder processing)
  set(part_sources ${OPENH264_COMMON} ${OPENH264_ASM_SOURCES})
  list(FILTER part_sources INCLUDE REGEX "/codec/${part}/")
  add_library(openh264_${part} OBJECT ${part_sources})
  target_include_directories(openh264_${part} PRIVATE ${OPENH264_COMMON_INCLUDES} "${OPENH264_ASM_INCLUDE}")
  if(part STREQUAL "encoder" OR part STREQUAL "decoder")
    target_include_directories(openh264_${part} PRIVATE
      "${OPENH264_ROOT}/codec/${part}/core/inc" "${OPENH264_ROOT}/codec/${part}/plus/inc")
  endif()
  if(part STREQUAL "encoder" OR part STREQUAL "processing")
    target_include_directories(openh264_${part} PRIVATE ${OPENH264_PROCESSING_INCLUDES})
  endif()
  target_compile_definitions(openh264_${part} PRIVATE GENERATED_VERSION_HEADER ${OPENH264_DEFINES})
  target_compile_options(openh264_${part} PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-fno-strict-aliasing>")
  if(NOT WIN32)
    target_compile_options(openh264_${part} PRIVATE "$<$<COMPILE_LANGUAGE:CXX>:-fstack-protector-all>")
  endif()
  target_sources(openh264 PRIVATE $<TARGET_OBJECTS:openh264_${part}>)
endforeach()
