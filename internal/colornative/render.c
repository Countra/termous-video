//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"

int tv_color_process(tv_color *s, const uint8_t *input, size_t length, int w,
                     int h, int stride, float white, uint8_t *output,
                     size_t output_length, int output_stride) {
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
  if (!tv_color_textures(s, w, h) ||
      !pl_tex_upload(s->gpu, pl_tex_transfer_params(.tex = s->input,
                                                    .ptr = (void *)input,
                                                    .row_pitch = stride)))
    return 1;
  pl_dispatch_reset_frame(s->dispatch);
  pl_shader sh = pl_dispatch_begin(s->dispatch);
  if (!sh)
    return 1;
  if (!tv_color_shader(s, sh, gain)) {
    pl_dispatch_abort(s->dispatch, &sh);
    return 1;
  }
  if (!pl_dispatch_finish(s->dispatch,
          pl_dispatch_params(.shader = &sh, .target = s->output))) {
    if (sh)
      pl_dispatch_abort(s->dispatch, &sh);
    return 1;
  }
  return pl_tex_download(s->gpu,
                         pl_tex_transfer_params(.tex = s->output, .ptr = output,
                                                .row_pitch = output_stride))
             ? 0
             : 1;
}
