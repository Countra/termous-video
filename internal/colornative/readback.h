#pragma once
#include "state.h"

enum { TV_COLOR_OK, TV_COLOR_FAILED, TV_COLOR_INVALID, TV_COLOR_BUSY, TV_COLOR_UNAVAILABLE };
#define TV_COLOR_SLOTS 2

struct tv_readback_slot {
  pl_tex output;
  uint64_t sequence;
  int occupied, discarded;
  tv_color_timings timings;
#ifdef _WIN32
  ID3D11Texture2D *texture, *staging;
  ID3D11Query *event, *disjoint, *ticks[4];
#else
  pl_buf buffer, upload;
  pl_timer timers[3];
  uint64_t timer_sequence, timer_values[3];
#endif
};

struct tv_readback {
  int width, height, measure, poisoned;
  size_t pitch, upload_pitch;
  struct tv_readback_slot slots[TV_COLOR_SLOTS];
#ifdef _WIN32
  ID3D11DeviceContext *context;
#endif
};

int tv_readback_create(tv_color *s);
int tv_readback_ready(tv_color *s, struct tv_readback_slot *slot);
int tv_readback_copy(tv_color *s, struct tv_readback_slot *slot, uint8_t *out, int stride);
int tv_readback_submit(tv_color *s, struct tv_readback_slot *slot, const uint8_t *input, int stride, float gain);
void tv_readback_release(tv_color *s);
