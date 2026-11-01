#pragma once
#include "pixels.h"
#include <x264.h>

struct tv_encoder {
    x264_t* codec = nullptr;
    tv_config config{};
    bool unusable = false;
    int64_t sequence = 0;
    std::vector<uint8_t> source, scaled;
#ifdef TERMOUS_VIDEO_FIXTURE
    int fault = 0;
#endif
    ~tv_encoder();
};
bool tv_parameters(x264_param_t& params, tv_config config);
int tv_vbv_buffer_size(tv_config config);
bool tv_parameters_match(x264_t* codec, tv_config config);
int tv_prepare_rate(tv_encoder* encoder, tv_options options, tv_config& candidate);
int tv_encode(tv_encoder* encoder, tv_i420 frame, tv_options options, tv_output* output);
