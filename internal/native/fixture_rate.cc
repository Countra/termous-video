//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"
#include <memory>

// 故障字段只存在于夹具构建，逐实例验证拒绝和应用后失败的边界。
extern "C" int tv_test_rate() {
    tv_encoder* raw=nullptr;
    if (tv_create({320,180,500000,15,31,0,1},&raw)!=TV_OK) return 1;
    std::unique_ptr<tv_encoder> e(raw);
    std::vector<uint8_t> pixels;
    auto f=tv_buffer(pixels,320,180);
    tv_output out{};
    if (tv_encode(e.get(),f,{},&out)!=TV_OK) return 2;
    e->fault=1;
    tv_options rate{0,0,1000000,15,1};
    if (tv_encode(e.get(),f,rate,&out)!=TV_FAILED || e->unusable ||
        e->config.bitrate!=500000 || out.data || e->sequence!=1) return 3;
    if (tv_encode(e.get(),f,{},&out)!=TV_OK || out.keyframe) return 4;
    if (tv_encode(e.get(),f,rate,&out)!=TV_OK || e->config.bitrate!=1000000 || out.keyframe) return 5;
    e->fault=2;
    rate.bitrate=750000;
    if (tv_encode(e.get(),f,rate,&out)!=TV_UNUSABLE || out.data || !e->unusable) return 6;
    if (tv_encode(e.get(),f,{},&out)!=TV_UNUSABLE) return 7;
    raw=nullptr;
    if (tv_create({320,180,500000,15,31,0,1},&raw)!=TV_OK) return 8;
    e.reset(raw);
    e->fault=3;
    if (tv_encode(e.get(),f,rate,&out)!=TV_UNUSABLE || out.data || e->config.bitrate!=500000) return 9;
    return 0;
}
