#include "codec_check.h"

#include <cstdio>
#include <initializer_list>

extern "C" int video_sdk_smoke() {
  try {
#ifndef VIDEO_SDK_ENCODER_ONLY
    const int api_error = check_openh264_api();
    if (api_error) {
      std::fprintf(stderr, "OpenH264 API check failed: stage=%d\n", api_error);
      return api_error;
    }
#endif
    for (int threads : {1, 8}) {
#ifdef VIDEO_SDK_ENCODER_ONLY
      const int error = encode_sequence(threads, nullptr, nullptr);
#else
      const int error = decode_sequence(threads);
#endif
      if (error) {
        std::fprintf(stderr, "Codec check failed: threads=%d stage=%d\n", threads, error);
        return error;
      }
    }
    return 0;
  } catch (...) {
    std::fputs("Synthetic codec check raised an exception\n", stderr);
    return 99;
  }
}
