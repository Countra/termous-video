//go:build cgo && !android && !ios && ((linux && amd64) || (darwin && arm64))

#include "readback.h"
#include "timing.h"
#include <string.h>

int tv_readback_create(tv_color *s) {
  struct tv_readback *r = s->readback;
  pl_fmt format = pl_find_fmt(s->gpu, PL_FMT_UNORM, 4, 8, 8,
      PL_FMT_CAP_RENDERABLE | PL_FMT_CAP_HOST_READABLE);
  if (!format) return 0;
  for (int i = 0; i < TV_COLOR_SLOTS; i++) {
    struct tv_readback_slot *slot = &r->slots[i];
    slot->output = pl_tex_create(s->gpu, pl_tex_params(.w = r->width, .h = r->height,
        .format = format, .renderable = true, .host_readable = true));
    slot->buffer = pl_buf_create(s->gpu, pl_buf_params(.size = r->pitch * r->height,
        .host_readable = true, .host_mapped = true, .memory_type = PL_BUF_MEM_HOST));
    slot->upload = pl_buf_create(s->gpu, pl_buf_params(.size = r->upload_pitch * r->height,
        .host_writable = true, .host_mapped = true, .memory_type = PL_BUF_MEM_HOST));
    if (!slot->output || !slot->buffer || !slot->upload) return 0;
    if (r->measure) for (int j = 0; j < 3; j++) slot->timers[j] = pl_timer_create(s->gpu);
  }
  return 1;
}

static void query_timings(tv_color *s, struct tv_readback_slot *slot) {
  if (!slot->timer_sequence) return;
  for (int j = 0; j < 3; j++)
    if (!slot->timer_values[j]) slot->timer_values[j] = pl_timer_query(s->gpu, slot->timers[j]);
  if (!slot->timer_values[0] || !slot->timer_values[1] || !slot->timer_values[2]) return;
  if (slot->timer_sequence == slot->sequence) {
    slot->timings.upload_gpu_ns = slot->timer_values[0];
    slot->timings.gpu_ns = slot->timer_values[1];
    slot->timings.download_gpu_ns = slot->timer_values[2];
    slot->timings.gpu_valid = 1;
  }
  slot->timer_sequence = 0;
}

int tv_readback_submit(tv_color *s, struct tv_readback_slot *slot, const uint8_t *input, int stride, float gain) {
  struct tv_readback *r = s->readback;
  query_timings(s, slot);
  // 上次查询未完成时跳过本帧诊断，不能把迟到的样本归给新任务。
  int measure_gpu = r->measure && !slot->timer_sequence && slot->timers[0] && slot->timers[1] && slot->timers[2];
  if (measure_gpu) {
    slot->timer_sequence = slot->sequence;
    memset(slot->timer_values, 0, sizeof(slot->timer_values));
  }
  uint64_t start = r->measure ? tv_color_now() : 0;
  for (int y = 0; y < r->height; y++)
    memcpy(slot->upload->data + (size_t)y * r->upload_pitch, input + (size_t)y * stride, (size_t)r->width * 8);
  if (!pl_tex_upload(s->gpu, pl_tex_transfer_params(.tex = s->input, .buf = slot->upload,
      .row_pitch = r->upload_pitch, .timer = measure_gpu ? slot->timers[0] : NULL))) return 0;
  if (r->measure) { slot->timings.upload_ns = tv_color_now() - start; start = tv_color_now(); }
  if (!tv_color_dispatch(s, slot->output, gain, measure_gpu ? slot->timers[1] : NULL)) return 0;
  if (r->measure) { slot->timings.dispatch_ns = tv_color_now() - start; start = tv_color_now(); }
  if (!pl_tex_download(s->gpu, pl_tex_transfer_params(.tex = slot->output, .buf = slot->buffer,
      .row_pitch = r->pitch, .timer = measure_gpu ? slot->timers[2] : NULL))) return 0;
  if (r->measure) slot->timings.download_ns = tv_color_now() - start;
  return 1;
}

int tv_readback_ready(tv_color *s, struct tv_readback_slot *slot) {
  return pl_buf_poll(s->gpu, slot->buffer, 0) || pl_buf_poll(s->gpu, slot->upload, 0) ? TV_COLOR_BUSY : TV_COLOR_OK;
}

int tv_readback_copy(tv_color *s, struct tv_readback_slot *slot, uint8_t *out, int stride) {
  struct tv_readback *r = s->readback;
  uint64_t start = r->measure ? tv_color_now() : 0;
  if (out) for (int y = 0; y < r->height; y++)
    memcpy(out + (size_t)y * stride, slot->buffer->data + (size_t)y * r->pitch, (size_t)r->width * 4);
  if (r->measure) slot->timings.copy_ns = tv_color_now() - start;
  query_timings(s, slot);
  return TV_COLOR_OK;
}

void tv_readback_release(tv_color *s) {
  for (int i = 0; i < TV_COLOR_SLOTS; i++) {
    struct tv_readback_slot *slot = &s->readback->slots[i];
    pl_tex_destroy(s->gpu, &slot->output);
    pl_buf_destroy(s->gpu, &slot->buffer);
    pl_buf_destroy(s->gpu, &slot->upload);
    for (int j = 0; j < 3; j++) pl_timer_destroy(s->gpu, &slot->timers[j]);
  }
}
