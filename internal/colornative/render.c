//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/tone_mapping.h>
#include <math.h>
#include <string.h>

static int textures(tv_color *s, int w, int h) {
  if (s->input && s->output && s->input->params.w == w &&
      s->input->params.h == h)
    return 1;
  pl_tex_destroy(s->gpu, &s->input);
  pl_tex_destroy(s->gpu, &s->output);
  pl_fmt in =
      pl_find_fmt(s->gpu, PL_FMT_FLOAT, 4, 16, 16, PL_FMT_CAP_SAMPLEABLE);
  pl_fmt out = pl_find_fmt(s->gpu, PL_FMT_UNORM, 4, 8, 8,
                           PL_FMT_CAP_RENDERABLE | PL_FMT_CAP_HOST_READABLE);
  if (!in || !out)
    return 0;
  s->input = pl_tex_create(s->gpu, pl_tex_params(.w = w, .h = h, .format = in,
                                                 .sampleable = true,
                                                 .host_writable = true));
  s->output = pl_tex_create(s->gpu, pl_tex_params(.w = w, .h = h, .format = out,
                                                  .renderable = true,
                                                  .host_readable = true));
  return s->input && s->output;
}
int tv_color_process(tv_color *s, const uint8_t *input, size_t length, int w,
                     int h, int stride, float peak, uint8_t *output,
                     size_t output_length, int output_stride) {
  if (!s || !input || !output || w < 1 || h < 1 ||
      (uint64_t)w * h > 16 * 1024 * 1024 || stride < (int64_t)w * 8 ||
      output_stride < (int64_t)w * 4 ||
      length < (uint64_t)(h - 1) * stride + w * 8 ||
      output_length < (uint64_t)(h - 1) * output_stride + w * 4 ||
      !isfinite(peak) || peak < 0 || peak > 10000)
    return 2;
  // 浮点特殊值不是可用像素，拒绝整帧，避免不同 GPU 的未定义颜色传播。
  for (int y = 0; y < h; y++)
    for (int x = 0; x < w * 4; x++) {
      uint16_t v;
      memcpy(&v, input + (size_t)y * stride + x * 2, 2);
      if ((v & 0x7c00) == 0x7c00)
        return 2;
    }
  if (!textures(s, w, h) ||
      !pl_tex_upload(s->gpu, pl_tex_transfer_params(.tex = s->input,
                                                    .ptr = (void *)input,
                                                    .row_pitch = stride)))
    return 1;
  struct pl_frame src = {
      .num_planes = 1,
      .planes = {{.texture = s->input,
                  .components = 4,
                  .component_mapping = {0, 1, 2, 3}}},
      .repr = {.sys = PL_COLOR_SYSTEM_RGB,
               .levels = PL_COLOR_LEVELS_FULL,
               .alpha = PL_ALPHA_INDEPENDENT},
      .color = {.primaries = PL_COLOR_PRIM_BT_709,
                .transfer = PL_COLOR_TRC_SCRGB,
                .hdr = {.min_luma = PL_COLOR_HDR_BLACK,
                        .max_luma = peak > 0 ? peak : 1000}}};
  struct pl_frame dst = {.num_planes = 1,
                         .planes = {{.texture = s->output,
                                     .components = 4,
                                     .component_mapping = {2, 1, 0, 3}}},
                         .repr = {.sys = PL_COLOR_SYSTEM_RGB,
                                  .levels = PL_COLOR_LEVELS_FULL,
                                  .alpha = PL_ALPHA_INDEPENDENT},
                         .color = pl_color_space_srgb};
  dst.color.hdr.min_luma = PL_COLOR_HDR_BLACK;
  dst.color.hdr.max_luma = 100;
  struct pl_color_map_params color = pl_color_map_default_params;
  color.tone_mapping_function = &pl_tone_map_bt2390;
  struct pl_render_params params = pl_render_default_params;
  params.color_map_params = &color;
  params.peak_detect_params = NULL;
  params.dither_params = NULL;
  if (!pl_render_image(s->renderer, &src, &dst, &params))
    return 1;
  return pl_tex_download(s->gpu,
                         pl_tex_transfer_params(.tex = s->output, .ptr = output,
                                                .row_pitch = output_stride))
             ? 0
             : 1;
}
