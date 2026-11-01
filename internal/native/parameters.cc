//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"
#include <algorithm>

int tv_vbv_buffer_size(tv_config c) {
    const int kbps = c.bitrate / 1000;
    return std::max((kbps + 3) / 4, (kbps + c.fps - 1) / c.fps);
}

bool tv_parameters(x264_param_t& p, tv_config c) {
    static_assert(X264_BIT_DEPTH == 8 && X264_CHROMA_FORMAT == X264_CSP_I420);
    if (x264_param_default_preset(&p, "superfast", "zerolatency") < 0) return false;
    p.i_width=c.width; p.i_height=c.height; p.i_csp=X264_CSP_I420;
    p.i_threads=c.threads; p.b_sliced_threads=1;
    p.i_fps_num=c.fps; p.i_fps_den=1;
    p.i_timebase_num=1; p.i_timebase_den=c.fps; p.b_vfr_input=0;
    p.i_keyint_max=c.fps*2; p.i_scenecut_threshold=0;
    p.i_bframe=0; p.rc.i_lookahead=0; p.i_sync_lookahead=0;
    p.i_level_idc=c.level; p.b_repeat_headers=1; p.b_annexb=1;
    // 原生库不逐帧打印；错误由稳定的 C ABI 状态映射至宿主诊断。
    p.i_log_level=X264_LOG_NONE;
    p.rc.i_rc_method=X264_RC_ABR;
    p.rc.i_bitrate=p.rc.i_vbv_max_bitrate=c.bitrate/1000;
    p.rc.i_vbv_buffer_size=tv_vbv_buffer_size(c);
    p.rc.b_filler=0; p.i_nal_hrd=X264_NAL_HRD_NONE;
    p.vui.i_vidformat=5; p.vui.b_fullrange=0;
    p.vui.i_colorprim=1; p.vui.i_transfer=13; p.vui.i_colmatrix=c.matrix==709 ? 1 : 6;
    return x264_param_apply_profile(&p, "baseline") == 0;
}

bool tv_parameters_match(x264_t* codec, tv_config c) {
    x264_param_t p{};
    x264_encoder_parameters(codec, &p);
    return p.i_width==c.width && p.i_height==c.height && p.i_level_idc==c.level &&
        p.i_fps_num==uint32_t(c.fps) && p.i_fps_den==1 && p.i_threads==c.threads &&
        bool(p.b_sliced_threads)==(c.threads>1) && !p.i_bframe && !p.rc.i_lookahead && !p.i_sync_lookahead &&
        p.rc.i_rc_method==X264_RC_ABR && p.rc.i_bitrate==c.bitrate/1000 &&
        p.rc.i_vbv_max_bitrate==c.bitrate/1000 && p.rc.i_vbv_buffer_size==tv_vbv_buffer_size(c) &&
        p.i_timebase_num==1 && p.i_timebase_den==uint32_t(c.fps) && !p.b_vfr_input &&
        p.b_repeat_headers && p.b_annexb && !p.b_cabac && !p.analyse.b_transform_8x8 &&
        p.i_keyint_max==c.fps*2 && !p.i_scenecut_threshold &&
        !p.vui.b_fullrange && p.vui.i_colorprim==1 && p.vui.i_transfer==13 && p.vui.i_colmatrix==(c.matrix==709 ? 1 : 6) &&
        !p.rc.b_filler && p.i_nal_hrd==X264_NAL_HRD_NONE &&
        x264_encoder_maximum_delayed_frames(codec)==0;
}
