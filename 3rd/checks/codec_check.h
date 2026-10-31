#pragma once

#include <cstdint>

constexpr int kFrameWidth = 512;
constexpr int kFrameHeight = 512;
constexpr int kFrameCount = 12;
constexpr int kBlockSize = 64;

using FrameConsumer = int (*)(const uint8_t*, int, int, void*);

void fill_pattern(uint8_t* bgra, int frame);
int check_pixels(unsigned char* const planes[3], const int strides[3], int frame);
int encode_sequence(int threads, FrameConsumer consume, void* context);
int decode_sequence(int threads);
int check_openh264_api();
