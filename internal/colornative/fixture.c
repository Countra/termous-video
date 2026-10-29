//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "state.h"

struct dispatch_check { int count, changed; uint64_t signature; };
static void record_dispatch(void *priv, const struct pl_dispatch_info *info) {
  struct dispatch_check *check = priv;
  if (check->count && check->signature != info->signature)
    check->changed = 1;
  check->signature = info->signature;
  check->count++;
}

// 仅合成测试编译此入口，不给生产处理器增加计数器或故障注入开关。
int tv_color_test_dispatch(void) {
  // 穷举每个槽的全部 binary16 位型，确认批量检查不会遗漏 NaN/Inf 或拒绝有限值。
  for (int channel = 0; channel < 4; channel++)
    for (uint32_t value = 0; value <= UINT16_MAX; value++) {
      uint64_t bits = (uint64_t)value << (channel * 16);
      if (tv_color_pixels_valid((uint8_t *)&bits, 1, 1, 8) !=
          ((value & 0x7c00) != 0x7c00))
        return 4;
    }
  tv_color *s = tv_color_create(0);
  if (!s) return 1;
  struct dispatch_check check = {0};
  pl_dispatch_callback(s->dispatch, &check, record_dispatch);
  uint16_t input[8] = {0x3c00, 0x3400, 0x4400, 0x3c00,
                       0x3c00, 0x3400, 0x4400, 0x3c00};
  uint8_t output[8];
  const float whites[] = {80, 120, 200, 300, 400, 80};
  int result = 0;
  for (int i = 0; i < 6; i++) {
    if (tv_color_process(s, (uint8_t *)input, sizeof(input), 2, 1, 16,
                         whites[i], output, sizeof(output), 8) ||
        check.count != i + 1 || check.changed) {
      result = 2;
      break;
    }
  }
  input[0] = 0x7c00;
  if (!result && (tv_color_process(s, (uint8_t *)input, sizeof(input), 2, 1, 16,
                                   80, output, sizeof(output), 8) != 2 ||
                  check.count != 6))
    result = 3;
  pl_dispatch_callback(s->dispatch, NULL, NULL);
  tv_color_destroy(s);
  return result;
}
