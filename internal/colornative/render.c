//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"
#include "timing.h"
#include "readback.h"

int tv_color_dispatch(tv_color *s, pl_tex target, float gain, pl_timer timer) {
  pl_dispatch_reset_frame(s->dispatch);
  pl_shader sh = pl_dispatch_begin(s->dispatch);
  if (!sh) return 0;
  if (!tv_color_shader(s, sh, gain) ||
      !pl_dispatch_finish(s->dispatch, pl_dispatch_params(.shader = &sh, .target = target, .timer = timer))) {
    if (sh) pl_dispatch_abort(s->dispatch, &sh);
    return 0;
  }
  return 1;
}

int tv_color_process(tv_color *s, const uint8_t *input, size_t length, int w,
                     int h, int stride, float white, uint8_t *output,
                     size_t output_length, int output_stride, tv_color_timings *timings) {
  uint64_t start = timings ? tv_color_now() : 0, checkpoint;
  if (timings)
    *timings = (tv_color_timings){0};
  float gain;
  if (!s || !input || !output || w < 1 || h < 1 ||
      (uint64_t)w * h > 16 * 1024 * 1024 || stride < (int64_t)w * 8 ||
      output_stride < (int64_t)w * 4 ||
      stride % 8 != 0 || output_stride % 4 != 0 ||
      length < (uint64_t)(h - 1) * stride + w * 8 ||
      output_length < (uint64_t)(h - 1) * output_stride + w * 4 ||
      !tv_color_gain(white, &gain))
    return 2;
  // 浮点特殊值不是可用像素，拒绝整帧，避免不同 GPU 的未定义颜色传播。
  if (!tv_color_pixels_valid(input, w, h, stride))
    return 2;
  if (s->readback) {
    for (int i = 0; i < TV_COLOR_SLOTS; i++) if (s->readback->slots[i].occupied) return TV_COLOR_BUSY;
    tv_readback_destroy(s);
  }
  if (timings) {
    checkpoint = tv_color_now();
    timings->validate_ns = checkpoint - start;
    start = checkpoint;
  }
  if (!tv_color_textures(s, w, h) ||
      !pl_tex_upload(s->gpu, pl_tex_transfer_params(.tex = s->input,
                                                    .ptr = (void *)input,
                                                    .no_import = true,
                                                    .row_pitch = stride)))
    return 1;
  if (timings) {
    checkpoint = tv_color_now();
    timings->upload_ns = checkpoint - start;
    start = checkpoint;
  }
  if (timings && !s->dispatch_timer) s->dispatch_timer = pl_timer_create(s->gpu);
  if (s->dispatch_timer_pending && pl_timer_query(s->gpu, s->dispatch_timer)) s->dispatch_timer_pending = 0;
  int measure_gpu = timings && s->dispatch_timer && !s->dispatch_timer_pending;
  if (measure_gpu) s->dispatch_timer_pending = 1;
  if (!tv_color_dispatch(s, s->output, gain, measure_gpu ? s->dispatch_timer : NULL)) {
    return 1;
  }
  if (timings) {
    checkpoint = tv_color_now();
    timings->dispatch_ns = checkpoint - start;
    timings->submit_ns = timings->upload_ns + timings->dispatch_ns;
    start = checkpoint;
  }
  // 同步下载包含 GPU 完成等待；单独报告，不能将它全部解释为 CPU 运算。
  int result = pl_tex_download(s->gpu,
                         pl_tex_transfer_params(.tex = s->output, .ptr = output,
                                                .row_pitch = output_stride))
             ? 0
             : 1;
  if (timings) {
    timings->download_ns = tv_color_now() - start;
    // 未完成的查询留待后续回收，不能把旧帧样本当成本帧耗时。
    if (measure_gpu) {
      timings->gpu_ns = pl_timer_query(s->gpu, s->dispatch_timer);
      if (timings->gpu_ns) s->dispatch_timer_pending = 0;
    }
  }
  return result;
}
