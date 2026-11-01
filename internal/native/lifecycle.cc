//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"
#include "encoder_limits.h"
#include <memory>

tv_encoder::~tv_encoder() { if (codec) x264_encoder_close(codec); }
extern "C" void tv_destroy(tv_encoder* encoder) { delete encoder; }

extern "C" int tv_create(tv_config c, tv_encoder** output) {
    if (!output) return TV_INVALID;
    *output=nullptr;
    if (!tv_config_valid(c)) return TV_INVALID;
    try {
        auto e=std::make_unique<tv_encoder>();
        // 显式约束切片行数，避免 x264 静默降低线程数后诊断仍显示请求值。
        c.threads=std::max(1, std::min(c.threads, ((c.height+15)/16)/4));
        struct Parameters { x264_param_t value{}; ~Parameters() { x264_param_cleanup(&value); } } params;
        if (!tv_parameters(params.value,c)) return TV_FAILED;
        e->codec=x264_encoder_open(&params.value);
        if (!e->codec || !tv_parameters_match(e->codec,c)) return TV_FAILED;
        e->config=c;
        *output=e.release();
        return TV_OK;
    } catch (...) { return TV_FAILED; }
}

extern "C" int tv_get_info(tv_encoder* e, tv_info* output) {
    if (!e || !e->codec || !output) return TV_INVALID;
    *output={"x264", X264_POINTVER, "superfast/zerolatency", e->config.threads};
    return TV_OK;
}
