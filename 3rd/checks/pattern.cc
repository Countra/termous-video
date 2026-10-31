#include "codec_check.h"

#include <cstdio>
#include <cstdlib>

namespace {
struct RGB { int r, g, b; };
constexpr RGB kColors[] = {
  {0, 0, 0}, {64, 64, 64}, {192, 192, 192}, {255, 255, 255},
  {255, 0, 0}, {0, 255, 0}, {0, 0, 255}, {255, 255, 0},
};

RGB color_at(int x, int y, int frame) {
  return kColors[(x / kBlockSize + y / kBlockSize + frame) % 8];
}

int reference_yuv(RGB c, int plane) {
  // 标量 BT.601 有限范围参考，不使用转换库或编码器的重建像素生成期望值。
  if (plane == 0) return ((66 * c.r + 129 * c.g + 25 * c.b + 128) >> 8) + 16;
  if (plane == 1) return ((-38 * c.r - 74 * c.g + 112 * c.b + 128) >> 8) + 128;
  return ((112 * c.r - 94 * c.g - 18 * c.b + 128) >> 8) + 128;
}
}

void fill_pattern(uint8_t* bgra, int frame) {
  for (int y = 0; y < kFrameHeight; ++y) {
    for (int x = 0; x < kFrameWidth; ++x) {
      const RGB c = color_at(x, y, frame);
      auto* pixel = bgra + (y * kFrameWidth + x) * 4;
      pixel[0] = static_cast<uint8_t>(c.b);
      pixel[1] = static_cast<uint8_t>(c.g);
      pixel[2] = static_cast<uint8_t>(c.r);
      pixel[3] = 255;
    }
  }
}

int check_pixels(unsigned char* const planes[3], const int strides[3], int frame) {
  for (int plane = 0; plane < 3; ++plane) {
    const int scale = plane == 0 ? 1 : 2;
    if (!planes[plane] || strides[plane] < kFrameWidth / scale) return 24;
    for (int y = 0; y < kFrameHeight / scale; ++y) {
      for (int x = 0; x < kFrameWidth / scale; ++x) {
        const int bx = (x * scale) % kBlockSize, by = (y * scale) % kBlockSize;
        // 排除块边缘的有损压缩影响，检查所有色块内部而非单个采样点。
        if (bx < 8 || bx >= kBlockSize - 8 || by < 8 || by >= kBlockSize - 8) continue;
        const int expected = reference_yuv(color_at(x * scale, y * scale, frame), plane);
        const int actual = planes[plane][y * strides[plane] + x];
        if (std::abs(actual - expected) > 8) {
          std::fprintf(stderr, "Decoded pixel mismatch: frame=%d plane=%d x=%d y=%d expected=%d actual=%d\n",
                       frame, plane, x, y, expected, actual);
          return 25;
        }
      }
    }
  }
  return 0;
}
