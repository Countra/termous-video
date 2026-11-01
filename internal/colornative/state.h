#pragma once
#include "bridge.h"
#ifdef _WIN32
#define COBJMACROS
#endif
#include <libplacebo/dispatch.h>
#include <libplacebo/colorspace.h>
#ifdef _WIN32
#include <libplacebo/d3d11.h>
#else
#include <libplacebo/vulkan.h>
#endif
struct tv_color {
  pl_log log;
  pl_gpu gpu;
  pl_dispatch dispatch;
  pl_shader_obj color_map;
  float to_work[9];
  pl_tex input, output;
  pl_timer dispatch_timer;
  int dispatch_timer_pending;
  struct tv_readback *readback;
  char device_name[256];
#ifdef _WIN32
  pl_d3d11 device;
#else
  pl_vulkan device;
  void *loader;
#endif
};
int tv_color_textures(tv_color *s, int w, int h);
int tv_color_gain(float white, float *gain);
int tv_color_pixels_valid(const uint8_t *input, int w, int h, int stride);
int tv_color_shader(tv_color *s, pl_shader sh, float gain);
int tv_color_input(tv_color *s, int w, int h);
int tv_color_dispatch(tv_color *s, pl_tex target, float gain, pl_timer timer);
void tv_readback_destroy(tv_color *s);
