//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "readback.h"
#include "timing.h"
#include <stdlib.h>
#include <string.h>

static int layout(tv_color *s, int w, int h, uint64_t *host, uint64_t *device, size_t *row_pitch, size_t *upload_pitch) {
  if (!s || !host || !device || w < 1 || h < 1 || (uint64_t)w * h > 16 * 1024 * 1024)
    return TV_COLOR_INVALID;
  if (w > s->gpu->limits.max_tex_2d_dim || h > s->gpu->limits.max_tex_2d_dim) return TV_COLOR_UNAVAILABLE;
  size_t align = 4096;
#ifndef _WIN32
  if (!s->gpu->limits.buf_transfer) return TV_COLOR_UNAVAILABLE;
  align = s->gpu->limits.align_tex_xfer_pitch;
  if (align < 8) align = 8;
  // 输出像素与传输步长同时满足对齐约束。
  while (align % 8) {
    if (align > SIZE_MAX / 2) return TV_COLOR_UNAVAILABLE;
    align *= 2;
  }
#endif
  size_t row = (size_t)w * 4;
  if (align > SIZE_MAX - (size_t)w * 8 + 1) return TV_COLOR_UNAVAILABLE;
  size_t pitch = (row + align - 1) / align * align;
  if (pitch < row || pitch > SIZE_MAX / (size_t)h / TV_COLOR_SLOTS) return TV_COLOR_INVALID;
#ifndef _WIN32
  if (pitch * (size_t)h > s->gpu->limits.max_buf_size) return TV_COLOR_UNAVAILABLE;
#endif
  *host = pitch * (size_t)h * TV_COLOR_SLOTS;
  *row_pitch = pitch;
  *upload_pitch = 0;
#ifndef _WIN32
  // 显式上传槽替代库内隐式指针暂存池，让新增主存占用可提前预约。
  *upload_pitch = ((size_t)w * 8 + align - 1) / align * align;
  if (*upload_pitch > SIZE_MAX / (size_t)h / TV_COLOR_SLOTS ||
      *upload_pitch * (size_t)h > s->gpu->limits.max_buf_size) return TV_COLOR_UNAVAILABLE;
  uint64_t uploads = *upload_pitch * (size_t)h * TV_COLOR_SLOTS;
  if (*host > UINT64_MAX - uploads) return TV_COLOR_INVALID;
  *host += uploads;
#endif
  *device = (uint64_t)w * h * (8 + 4 * TV_COLOR_SLOTS);
  return TV_COLOR_OK;
}

int tv_color_async_plan(tv_color *s, int w, int h, uint64_t *host, uint64_t *device) {
  size_t pitch, upload_pitch;
  return layout(s,w,h,host,device,&pitch,&upload_pitch);
}

int tv_color_async_prepare(tv_color *s, int w, int h, int measure) {
  uint64_t host, device;
  size_t pitch, upload_pitch;
  int status = layout(s, w, h, &host, &device, &pitch, &upload_pitch);
  if (status) return status;
  if (s->readback) {
    for (int i = 0; i < TV_COLOR_SLOTS; i++) if (s->readback->slots[i].occupied) return TV_COLOR_BUSY;
    if (!s->readback->poisoned && s->readback->width == w && s->readback->height == h && s->readback->measure == measure)
      return TV_COLOR_OK;
    tv_readback_destroy(s);
  }
  if (!tv_color_input(s, w, h)) return pl_gpu_is_failed(s->gpu) ? TV_COLOR_FAILED : TV_COLOR_UNAVAILABLE;
  pl_tex_destroy(s->gpu, &s->output);
  s->readback = calloc(1, sizeof(*s->readback));
  if (!s->readback) return TV_COLOR_UNAVAILABLE;
  s->readback->width = w; s->readback->height = h;
  s->readback->pitch = pitch;
  s->readback->upload_pitch = upload_pitch;
  s->readback->measure = measure;
  if (tv_readback_create(s)) return TV_COLOR_OK;
  tv_readback_destroy(s);
  return pl_gpu_is_failed(s->gpu) ? TV_COLOR_FAILED : TV_COLOR_UNAVAILABLE;
}

static struct tv_readback_slot *find_slot(tv_color *s, uint64_t sequence) {
  if (!s || !s->readback || !sequence) return NULL;
  for (int i = 0; i < TV_COLOR_SLOTS; i++) {
    struct tv_readback_slot *slot = &s->readback->slots[i];
    if (slot->occupied && slot->sequence == sequence) return slot;
  }
  return NULL;
}

int tv_color_async_submit(tv_color *s, const uint8_t *input, size_t length, int stride, float white, uint64_t sequence) {
  if (!s || !s->readback || !input || !sequence) return TV_COLOR_INVALID;
  struct tv_readback *r = s->readback;
  if (r->poisoned) return TV_COLOR_FAILED;
  int w = r->width, h = r->height;
  if (stride < (int64_t)w * 8 || stride % 8 || length < (uint64_t)(h - 1) * stride + w * 8 || find_slot(s, sequence))
    return TV_COLOR_INVALID;
  struct tv_readback_slot *slot = NULL;
  for (int i = 0; i < TV_COLOR_SLOTS; i++) if (!r->slots[i].occupied) { slot = &r->slots[i]; break; }
  if (!slot) return TV_COLOR_BUSY;
  uint64_t start = r->measure ? tv_color_now() : 0;
  float gain;
  if (!tv_color_gain(white, &gain) || !tv_color_pixels_valid(input, w, h, stride)) return TV_COLOR_INVALID;
  slot->timings = (tv_color_timings){0};
  if (r->measure) slot->timings.validate_ns = tv_color_now() - start;
  // 先占用槽；部分提交失败时仅能经过安全收尾，不能覆盖潜在在途命令。
  slot->sequence = sequence; slot->occupied = 1; slot->discarded = 0;
  if (!tv_readback_submit(s, slot, input, stride, gain)) {
    r->poisoned = 1;
    return TV_COLOR_FAILED;
  }
  pl_gpu_flush(s->gpu);
  if (r->measure) slot->timings.submit_ns = tv_color_now() - start - slot->timings.validate_ns;
  return TV_COLOR_OK;
}

int tv_color_async_ready(tv_color *s, uint64_t sequence) {
  struct tv_readback_slot *slot = find_slot(s, sequence);
  if (!slot) return TV_COLOR_INVALID;
  if (s->readback->poisoned || pl_gpu_is_failed(s->gpu)) return TV_COLOR_FAILED;
  return tv_readback_ready(s, slot);
}

int tv_color_async_discard(tv_color *s, uint64_t sequence) {
  struct tv_readback_slot *slot = find_slot(s, sequence);
  if (!slot) return TV_COLOR_INVALID;
  slot->discarded = 1;
  return TV_COLOR_OK;
}

int tv_color_async_collect(tv_color *s, uint64_t sequence, uint8_t *out, size_t length, int stride, tv_color_timings *timings) {
  struct tv_readback_slot *slot = find_slot(s, sequence);
  if (!slot) return TV_COLOR_INVALID;
  int status = tv_color_async_ready(s, sequence);
  if (status) return status;
  int w = s->readback->width, h = s->readback->height;
  if (!slot->discarded && (!out || stride < (int64_t)w * 4 || stride % 4 || length < (uint64_t)(h - 1) * stride + w * 4))
    return TV_COLOR_INVALID;
  status = tv_readback_copy(s, slot, slot->discarded ? NULL : out, stride);
  if (status) {
    if (status != TV_COLOR_BUSY) s->readback->poisoned = 1;
    return status;
  }
  if (timings) *timings = slot->timings;
  slot->occupied = 0;
  return TV_COLOR_OK;
}

void tv_readback_destroy(tv_color *s) {
  if (!s || !s->readback) return;
  // 析构允许等待；正常完成查询不进行全局 GPU 等待。
  pl_gpu_finish(s->gpu);
  tv_readback_release(s);
  free(s->readback);
  s->readback = NULL;
}
