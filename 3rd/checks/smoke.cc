#include <cstdint>
#include <cstdio>
#include <memory>
#include <vector>
#include <x264.h>
#include <libyuv.h>

namespace {
struct Parameters {
  x264_param_t value{};
  ~Parameters() { x264_param_cleanup(&value); }
};

// 只核验编码输出的结构，不把 NAL 检查表述为跨端解码验收。
bool check_nals(x264_nal_t* nals, int count, int bytes, bool keyframe) {
  if (!nals || count <= 0 || bytes <= 0) return false;
  int total = 0;
  bool sps = false, pps = false, idr = false, slice = false;
  for (int i = 0; i < count; ++i) {
    const auto& nal = nals[i];
    const int start = nal.b_long_startcode ? 4 : 3;
    if (!nal.p_payload || nal.i_payload <= start || nal.i_payload > bytes - total) return false;
    total += nal.i_payload;
    for (int j = 0; j < start - 1; ++j) if (nal.p_payload[j] != 0) return false;
    if (nal.p_payload[start - 1] != 1 || (nal.p_payload[start] & 31) != nal.i_type) return false;
    if (nal.i_type == NAL_SPS) {
      if (nal.i_payload < start + 4 || nal.p_payload[start + 1] != 66 ||
          (nal.p_payload[start + 2] & 0xc0) != 0xc0 || nal.p_payload[start + 3] != 51) return false;
      sps = true;
    }
    pps |= nal.i_type == NAL_PPS;
    idr |= nal.i_type == NAL_SLICE_IDR;
    slice |= nal.i_type == NAL_SLICE;
  }
  return total == bytes && (keyframe ? sps && pps && idr : slice && !idr);
}

int encode(int threads) {
  constexpr int width = 512, height = 512;
  Parameters params;
  auto& p = params.value;
  if (x264_param_default_preset(&p, "ultrafast", "zerolatency") < 0) return 1;
  p.i_width = width;
  p.i_height = height;
  p.i_csp = X264_CSP_I420;
  p.i_threads = threads;
  p.b_sliced_threads = 1;
  p.i_fps_num = 60;
  p.i_fps_den = 1;
  p.i_timebase_num = 1;
  p.i_timebase_den = 60;
  p.b_vfr_input = 0;
  p.i_keyint_max = 120;
  p.i_level_idc = 51;
  p.b_repeat_headers = 1;
  p.b_annexb = 1;
  p.i_log_level = X264_LOG_ERROR;
  p.rc.i_rc_method = X264_RC_ABR;
  p.rc.i_bitrate = p.rc.i_vbv_max_bitrate = 100000;
  p.rc.i_vbv_buffer_size = 100000;
  if (x264_param_apply_profile(&p, "baseline") < 0) return 2;
  std::unique_ptr<x264_t, decltype(&x264_encoder_close)> encoder(x264_encoder_open(&p), x264_encoder_close);
  if (!encoder) return 3;
  x264_param_t applied{};
  x264_encoder_parameters(encoder.get(), &applied);
  if (applied.i_threads != threads || applied.i_bframe || applied.rc.i_lookahead ||
      applied.i_sync_lookahead || applied.i_level_idc != 51 ||
      x264_encoder_maximum_delayed_frames(encoder.get()) != 0) return 4;

  std::vector<uint8_t> bgra(width * height * 4), pixels(width * height * 3 / 2);
  x264_picture_t input{}, output{};
  x264_picture_init(&input);
  input.img.i_csp = X264_CSP_I420;
  input.img.i_plane = 3;
  input.img.i_stride[0] = width;
  input.img.i_stride[1] = input.img.i_stride[2] = width / 2;
  input.img.plane[0] = pixels.data();
  input.img.plane[1] = pixels.data() + width * height;
  input.img.plane[2] = pixels.data() + width * height * 5 / 4;
  for (int frame = 0; frame < 12; ++frame) {
    for (int y = 0; y < height; ++y) {
      for (int x = 0; x < width; ++x) {
        auto* pixel = &bgra[(y * width + x) * 4];
        pixel[0] = static_cast<uint8_t>(x + frame * 17);
        pixel[1] = static_cast<uint8_t>(y + frame * 11);
        pixel[2] = static_cast<uint8_t>(x + y);
        pixel[3] = 255;
      }
    }
    if (libyuv::ARGBToI420(bgra.data(), width * 4, input.img.plane[0], width,
        input.img.plane[1], width / 2, input.img.plane[2], width / 2, width, height)) return 5;
    if (frame == 6) {
      x264_encoder_parameters(encoder.get(), &applied);
      applied.rc.i_bitrate = applied.rc.i_vbv_max_bitrate = 50000;
      if (x264_encoder_reconfig(encoder.get(), &applied) < 0) return 6;
    }
    const bool keyframe = frame == 0 || frame == 9;
    input.i_type = keyframe ? X264_TYPE_IDR : X264_TYPE_AUTO;
    input.i_pts = frame;
    x264_nal_t* nals = nullptr;
    int count = 0;
    const int bytes = x264_encoder_encode(encoder.get(), &nals, &count, &input, &output);
    if (!check_nals(nals, count, bytes, keyframe) || output.i_pts != frame || output.i_dts != frame ||
        bool(output.b_keyframe) != keyframe || x264_encoder_delayed_frames(encoder.get()) != 0) return 7;
    if (frame == 6) {
      x264_encoder_parameters(encoder.get(), &applied);
      if (applied.rc.i_bitrate != 50000 || applied.i_level_idc != 51) return 8;
    }
  }
  x264_nal_t* nals = nullptr;
  int count = 0;
  if (x264_encoder_encode(encoder.get(), &nals, &count, nullptr, &output) != 0 || count != 0) return 9;
  return 0;
}
}

extern "C" int video_sdk_smoke() {
  try {
    static_assert(X264_BIT_DEPTH == 8 && X264_CHROMA_FORMAT == X264_CSP_I420);
    for (int threads : {1, 8}) {
      const int error = encode(threads);
      if (error) {
        std::fprintf(stderr, "x264 smoke failed: threads=%d stage=%d\n", threads, error);
        return error;
      }
    }
    return 0;
  } catch (...) {
    std::fputs("Synthetic x264 check raised an exception\n", stderr);
    return 99;
  }
}
