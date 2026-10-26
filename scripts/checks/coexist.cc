#include <wels/codec_api.h>
#include <libyuv.h>
#include <cstdint>

// 两份翻译单元分别使用各自 SDK 的头文件，比较绑定地址以发现链接串用。
extern "C" uintptr_t video_check_binding(int entry) {
    return entry == 0 ? reinterpret_cast<uintptr_t>(&WelsCreateSVCEncoder)
                      : reinterpret_cast<uintptr_t>(&libyuv::ARGBToI420);
}
