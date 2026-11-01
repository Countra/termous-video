//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"
#include <math.h>
#include <string.h>
#if defined(__SSE2__)
#include <emmintrin.h>
#elif defined(__aarch64__)
#include <arm_neon.h>
#endif

int tv_color_gain(float white, float *gain) {
  if (!isfinite(white) || white <= 0 || white > 10000)
    return 0;
  // scRGB 80 nit → 桌面相对白色 → 100 nit 输出标尺 → libplacebo 203 nit 单位。
  *gain = (PL_COLOR_SCRGB_WHITE / PL_COLOR_SDR_WHITE * 100.0f) / white;
  return isfinite(*gain) && isfinite(*gain * 65504.0f * 4.0f);
}

int tv_color_pixels_valid(const uint8_t *input, int w, int h, int stride) {
  for (int y = 0; y < h; y++) {
    int x = 0;
    // 两像素一组检查全部分量，未对齐输入与奇数行尾仍保留标量边界。
#if defined(__SSE2__)
    const __m128i exponent = _mm_set1_epi16(0x7c00);
    for (; x + 1 < w; x += 2) {
      __m128i bits = _mm_loadu_si128((const __m128i *)(input + (size_t)y * stride + (size_t)x * 8));
      if (_mm_movemask_epi8(_mm_cmpeq_epi16(_mm_and_si128(bits, exponent), exponent))) return 0;
    }
#elif defined(__aarch64__)
    const uint16x8_t exponent = vdupq_n_u16(0x7c00);
    for (; x + 1 < w; x += 2) {
      uint16x8_t bits = vld1q_u16((const uint16_t *)(input + (size_t)y * stride + (size_t)x * 8));
      if (vmaxvq_u16(vceqq_u16(vandq_u16(bits, exponent), exponent))) return 0;
    }
#endif
    for (; x < w; x++) {
      uint64_t bits;
      memcpy(&bits, input + (size_t)y * stride + (size_t)x * 8, 8);
      // 一次检查四个半精度分量，保留原有整帧有限性校验，减少逐分量分支。
      // 每个 16 位槽的指数差在 0..0x7c00；减一后高位仅在存在零槽时置位。
      uint64_t missing = (bits & UINT64_C(0x7c007c007c007c00)) ^ UINT64_C(0x7c007c007c007c00);
      if ((missing - UINT64_C(0x0001000100010001)) & UINT64_C(0x8000800080008000))
        return 0;
    }
  }
  return 1;
}
