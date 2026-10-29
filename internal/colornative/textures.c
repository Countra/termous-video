//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"

int tv_color_textures(tv_color *s, int w, int h) {
  if (s->input && s->output && s->input->params.w == w &&
      s->input->params.h == h)
    return 1;
  pl_tex_destroy(s->gpu, &s->input);
  pl_tex_destroy(s->gpu, &s->output);
  pl_fmt in = pl_find_fmt(s->gpu, PL_FMT_FLOAT, 4, 16, 16, PL_FMT_CAP_SAMPLEABLE);
  pl_fmt out = pl_find_fmt(s->gpu, PL_FMT_UNORM, 4, 8, 8,
                         PL_FMT_CAP_RENDERABLE | PL_FMT_CAP_HOST_READABLE);
  if (!in || !out)
    return 0;
  s->input = pl_tex_create(s->gpu, pl_tex_params(.w = w, .h = h, .format = in,
      .sampleable = true, .host_writable = true));
  s->output = pl_tex_create(s->gpu, pl_tex_params(.w = w, .h = h, .format = out,
      .renderable = true, .host_readable = true));
  if (s->input && s->output)
    return 1;
  pl_tex_destroy(s->gpu, &s->input);
  pl_tex_destroy(s->gpu, &s->output);
  return 0;
}
