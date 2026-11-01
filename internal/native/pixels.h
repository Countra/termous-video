#pragma once
#include "bridge.h"
#include <termous_video_symbols.h>
#include <libyuv.h>
#include <vector>

bool tv_size(int width, int height);
bool tv_plane_valid(tv_plane plane, int width, int height);
bool tv_i420_valid(tv_i420 frame);
tv_i420 tv_buffer(std::vector<uint8_t>& buffer, int width, int height);
