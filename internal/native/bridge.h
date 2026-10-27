#pragma once
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct tv_encoder tv_encoder;
typedef struct { int width, height, bitrate, fps, level, matrix; } tv_config;
typedef struct { uint8_t* data; size_t length; int stride; } tv_plane;
typedef struct { tv_plane y, u, v; int width, height; } tv_i420;
typedef struct { const uint8_t* data; int length, keyframe, skipped; } tv_output;
enum { TV_OK = 0, TV_INVALID = 1, TV_FAILED = 2, TV_UNUSABLE = 3 };
int tv_create(tv_config config, tv_encoder** output);
void tv_destroy(tv_encoder* encoder);
int tv_rate(tv_encoder* encoder, int bitrate, int fps);
int tv_encode_bgra(tv_encoder* encoder, const uint8_t* pixels, size_t length, int width, int height, int stride, int keyframe, int64_t timestamp, tv_output* output);
int tv_encode_i420(tv_encoder* encoder, tv_i420 frame, int keyframe, int64_t timestamp, tv_output* output);
int tv_convert(const uint8_t* pixels, size_t length, int width, int height, int stride, tv_i420 output);
int tv_scale(tv_i420 source, tv_i420 output);
#ifdef __cplusplus
}
#endif
