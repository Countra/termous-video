include("${CMAKE_CURRENT_LIST_DIR}/libyuv_sources.cmake")
add_library(yuv STATIC ${LIBYUV_COMMON})
target_include_directories(yuv PRIVATE "${YUV_ROOT}/include")
# 不链接 JPEG，保留桌面视频所需的转换、缩放和运行时 SIMD 分派。
if(TERMOUS_TARGET STREQUAL "darwin/arm64")
  target_compile_definitions(yuv PRIVATE LIBYUV_DISABLE_SVE LIBYUV_DISABLE_SME)
  set(NEON_SOURCES
    "${YUV_ROOT}/source/compare_neon64.cc"
    "${YUV_ROOT}/source/rotate_neon64.cc"
    "${YUV_ROOT}/source/row_neon64.cc"
    "${YUV_ROOT}/source/scale_neon64.cc")
  target_sources(yuv PRIVATE ${NEON_SOURCES})
  set_source_files_properties(${NEON_SOURCES} PROPERTIES COMPILE_OPTIONS "-march=armv8.2-a+dotprod+i8mm")
endif()
