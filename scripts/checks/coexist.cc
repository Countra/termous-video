#include <libyuv.h>
#include <wels/codec_api.h>
#include <cstdint>

// 验证 video 的完整 OpenH264 和 libyuv 都没有解析到 RDP 的另一份依赖。
extern "C" void video_check_binding(uintptr_t entries[3]) {
    entries[0] = reinterpret_cast<uintptr_t>(&libyuv::ARGBToI420);
    entries[1] = reinterpret_cast<uintptr_t>(&WelsCreateDecoder);
    entries[2] = reinterpret_cast<uintptr_t>(&WelsCreateSVCEncoder);
}
