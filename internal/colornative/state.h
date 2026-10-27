#pragma once
#include "bridge.h"
#include <libplacebo/renderer.h>
#ifdef _WIN32
#include <libplacebo/d3d11.h>
#else
#include <libplacebo/vulkan.h>
#endif
struct tv_color {
  pl_log log;
  pl_gpu gpu;
  pl_renderer renderer;
  pl_tex input, output;
#ifdef _WIN32
  pl_d3d11 device;
#else
  pl_vulkan device;
  void *loader;
#endif
};
