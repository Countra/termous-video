//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"
#include <libplacebo/shaders/sampling.h>
#include <libplacebo/shaders/custom.h>
#include <libplacebo/shaders/colorspace.h>

int tv_color_shader(tv_color *s, pl_shader sh, float gain) {
  if (!pl_shader_sample_direct(sh, pl_sample_src(.tex = s->input, .components = 4)))
    return 0;
  struct pl_shader_var vars[] = {
      {.var = pl_var_float("desktop_gain"), .data = &gain, .dynamic = true},
      {.var = pl_var_mat3("desktop_to_work"), .data = s->to_work}};
  struct pl_custom_shader normalize = {
      .description = "Desktop white normalization",
      .input = PL_SHADER_SIG_COLOR, .output = PL_SHADER_SIG_COLOR,
      // 保留负分量，先做真实的原色矩阵转换，再交给库内置色域映射。
      .body = "color.rgb = desktop_to_work * (color.rgb * desktop_gain);",
      .variables = vars, .num_variables = 2};
  if (!pl_shader_custom(sh, &normalize))
    return 0;
  struct pl_color_space src = {
      .primaries = PL_COLOR_PRIM_BT_2020, .transfer = PL_COLOR_TRC_LINEAR,
      // 这是固定映射策略的参考范围，不是显示器峰值或内容元数据。
      .hdr = {.min_luma = PL_COLOR_HDR_BLACK, .max_luma = 1000}};
  struct pl_color_space dst = pl_color_space_srgb;
  dst.hdr.min_luma = PL_COLOR_HDR_BLACK;
  dst.hdr.max_luma = 100;
  struct pl_color_map_params params = pl_color_map_default_params;
  params.tone_mapping_function = &pl_tone_map_mobius;
  params.tone_constants.linear_knee = 0.9f;
  params.film_strength = 0;
  params.mastering_clip = 0;
  params.gamut_mapping = &pl_gamut_map_relative;
  params.gamut_expansion = false;
  params.inverse_tone_mapping = false;
  params.contrast_recovery = 0;
  // 只采用本函数构造的固定亮度范围。NONE 会忽略该范围并引入默认黑位补偿。
  // 不传入任何内容峰值、场景均值或动态探测状态。
  params.metadata = PL_HDR_METADATA_HDR10;
  pl_shader_color_map_ex(sh, &params, pl_color_map_args(
      .src = src, .dst = dst, .prelinearized = true, .state = &s->color_map));
  struct pl_custom_shader pack = {
      .input = PL_SHADER_SIG_COLOR, .output = PL_SHADER_SIG_COLOR,
      .body = "color = vec4(color.bgr, 1.0);"};
  return !pl_shader_is_failed(sh) && pl_shader_custom(sh, &pack);
}
