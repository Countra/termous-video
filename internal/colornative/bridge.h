#pragma once
#include <stddef.h>
#include <stdint.h>
typedef struct tv_color tv_color;
tv_color *tv_color_create(int software);
void tv_color_destroy(tv_color *state);
const char *tv_color_backend(tv_color *state);
const char *tv_color_device(tv_color *state);
typedef struct {
  uint64_t validate_ns, upload_ns, dispatch_ns, download_ns, gpu_ns;
  uint64_t map_ns, copy_ns, upload_gpu_ns, download_gpu_ns;
  uint64_t submit_ns;
  int gpu_valid;
} tv_color_timings;
int tv_color_failed(tv_color *state);
int tv_color_process(tv_color *state, const uint8_t *input, size_t input_length,
                     int width, int height, int stride, float white,
                     uint8_t *output, size_t output_length, int output_stride,
                     tv_color_timings *timings);
int tv_color_async_plan(tv_color*, int width, int height, uint64_t *host_bytes, uint64_t *device_bytes);
int tv_color_async_prepare(tv_color*, int width, int height, int measure);
int tv_color_async_submit(tv_color*, const uint8_t*, size_t length, int stride,
                          float white, uint64_t sequence);
int tv_color_async_ready(tv_color*, uint64_t sequence);
int tv_color_async_collect(tv_color*, uint64_t sequence, uint8_t*, size_t length,
                           int stride, tv_color_timings*);
int tv_color_async_discard(tv_color*, uint64_t sequence);
