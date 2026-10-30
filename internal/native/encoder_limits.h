#pragma once
#include "bridge.h"
#include <algorithm>

// 等级边界与产品上限取交集，创建编码器和独立 C ABI 校验共用该值。
inline int tv_level_bitrate(int level) {
  switch (level) {
  case 31: return 14000000;
  case 32: case 40: return 20000000;
  case 41: case 42: return 50000000;
  case 50: case 51: return 100000000;
  default: return 0;
  }
}

// C ABI 独立复核边界，防止直接原生调用绕过 Go 校验。
inline bool tv_config_valid(tv_config c) {
  if (c.width < 16 || c.height < 16 || c.width % 2 || c.height % 2 ||
      std::max(c.width, c.height) > 2560 ||
      std::min(c.width, c.height) > 1440 || c.bitrate < 100000 ||
      c.bitrate > tv_level_bitrate(c.level) || c.fps < 1 || c.fps > 60 ||
      (c.matrix != 0 && c.matrix != 709))
    return false;
  const int levels[][3] = {
      {31, 3600, 108000}, {32, 5120, 216000},
      {40, 8192, 245760}, {41, 8192, 245760},
      {42, 8704, 522240}, {50, 22080, 589824},
      {51, 36864, 983040}};
  const int mb = ((c.width + 15) / 16) * ((c.height + 15) / 16);
  for (auto &l : levels)
    if (l[0] == c.level)
      return mb <= l[1] && mb * c.fps <= l[2];
  return false;
}
