//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"

static bool apply(ISVCEncoder* codec, int bitrate, int fps) {
    SBitrateInfo rate{SPATIAL_LAYER_ALL,bitrate};
    float framerate=float(fps);
    // 两项都尝试写入，恢复路径不能因第一项失败跳过第二项。
    int a=codec->SetOption(ENCODER_OPTION_BITRATE,&rate);
    int b=codec->SetOption(ENCODER_OPTION_FRAME_RATE,&framerate);
    return a==0 && b==0;
}
extern "C" int tv_rate(tv_encoder* e, int bitrate, int fps) {
    if (!e || !e->codec || bitrate < 100000 || bitrate > 8000000 || fps < 1 || fps > 30) return TV_INVALID;
    if (e->unusable) return TV_UNUSABLE;
    try {
        if (apply(e->codec,bitrate,fps)) { e->config.bitrate=bitrate; e->config.fps=fps; return TV_OK; }
    } catch (...) {}
    try { if (apply(e->codec,e->config.bitrate,e->config.fps)) return TV_FAILED; } catch (...) {}
    e->unusable=true;
    return TV_UNUSABLE;
}
