//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"
#include "encoder_limits.h"

int tv_prepare_rate(tv_encoder* e, tv_options options, tv_config& candidate) {
    candidate=e->config;
    if (!options.rate_present) return TV_OK;
    candidate.bitrate=options.bitrate; candidate.fps=options.fps;
    if (!tv_config_valid(candidate)) return TV_INVALID;
    if (candidate.fps!=e->config.fps) return TV_RECONFIGURE;
    if (candidate.bitrate/1000==e->config.bitrate/1000) return TV_OK;
#ifdef TERMOUS_VIDEO_FIXTURE
    if (e->fault==1) { e->fault=0; return TV_FAILED; }
#endif
    x264_param_t p{};
    x264_encoder_parameters(e->codec,&p);
    p.rc.i_bitrate=p.rc.i_vbv_max_bitrate=candidate.bitrate/1000;
    p.rc.i_vbv_buffer_size=tv_vbv_buffer_size(candidate);
    // 此时只暂存到 x264；必须在本次编码成功并复核参数后提交配置。
    return x264_encoder_reconfig(e->codec,&p)==0 ? TV_OK : TV_FAILED;
}
