#pragma once
#include "bridge.h"
#include <termous_video_symbols.h>
#include <wels/codec_api.h>
#include <libyuv.h>
#include <vector>

struct tv_encoder {
    ISVCEncoder* codec = nullptr;
    tv_config config{};
    bool unusable = false;
    std::vector<uint8_t> source, scaled, output;
    ~tv_encoder();
};
bool tv_size(int width, int height);
bool tv_plane_valid(tv_plane plane, int width, int height);
bool tv_i420_valid(tv_i420 frame);
tv_i420 tv_buffer(std::vector<uint8_t>& buffer, int width, int height);
int tv_encode(tv_encoder* encoder, tv_i420 frame, int keyframe, int64_t timestamp, tv_output* output);
