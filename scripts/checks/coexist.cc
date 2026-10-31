#include <libyuv.h>
#include <cstdint>

// 两个编码器使用不同 API；只比较同名 libyuv 入口，确保没有链接到另一份依赖。
extern "C" uintptr_t video_check_binding() {
    return reinterpret_cast<uintptr_t>(&libyuv::ARGBToI420);
}
