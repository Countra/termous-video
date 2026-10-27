#pragma once
#include "bridge.h"
#include <algorithm>

// C ABI 独立复核边界，防止直接原生调用绕过 Go 校验。
inline bool tv_config_valid(tv_config c) {
  if (c.width < 16 || c.height < 16 || c.width % 2 || c.height % 2 ||
      std::max(c.width, c.height) > 2560 ||
      std::min(c.width, c.height) > 1440 || c.bitrate < 100000 ||
      c.bitrate > 24000000 || c.fps < 1 || c.fps > 60 ||
      (c.matrix != 0 && c.matrix != 709))
    return false;
  const int levels[][4] = {
      {31, 3600, 108000, 14000000}, {32, 5120, 216000, 20000000},
      {40, 8192, 245760, 20000000}, {41, 8192, 245760, 24000000},
      {42, 8704, 522240, 24000000}, {50, 22080, 589824, 24000000},
      {51, 36864, 983040, 24000000}};
  const int mb = ((c.width + 15) / 16) * ((c.height + 15) / 16);
  for (auto &l : levels)
    if (l[0] == c.level)
      return mb <= l[1] && mb * c.fps <= l[2] && c.bitrate <= l[3];
  return false;
}
