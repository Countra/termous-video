#include "check.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <libplacebo/renderer.h>
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/tone_mapping.h>

int placebo_render_check(pl_gpu gpu, pl_log log)
{
    enum { W = 64, H = 16 };
    // IEEE 754 binary16：0、0.25、1、4、12.5，对应 scRGB 0～1000 nit。
    const uint16_t values[] = {0x0000, 0x3400, 0x3c00, 0x4400, 0x4a40};
    uint16_t source[W * H * 4];
    uint8_t output[W * H * 4];
    for (int y = 0; y < H; ++y) {
        for (int x = 0; x < W; ++x) {
            size_t p = (y * W + x) * 4;
            uint16_t value = values[x * 5 / W];
            source[p] = source[p + 1] = source[p + 2] = value;
            if (y >= H / 2) {
                // 灰阶不能发现 RGB 通道交换，下半部分补充独立的三原色色块。
                for (int channel = 0; channel < 3; ++channel)
                    source[p + channel] = channel == x * 3 / W ? 0x3c00 : 0;
            }
            source[p + 3] = 0x3c00;
        }
    }
    pl_fmt input_fmt = pl_find_fmt(gpu, PL_FMT_FLOAT, 4, 16, 16, PL_FMT_CAP_SAMPLEABLE);
    pl_fmt output_fmt = pl_find_fmt(gpu, PL_FMT_UNORM, 4, 8, 8,
                                    PL_FMT_CAP_RENDERABLE | PL_FMT_CAP_HOST_READABLE);
    if (!input_fmt || !output_fmt)
        return 2;
    pl_tex input = pl_tex_create(gpu, pl_tex_params(
        .w = W, .h = H, .format = input_fmt, .sampleable = true, .initial_data = source));
    pl_tex target = pl_tex_create(gpu, pl_tex_params(
        .w = W, .h = H, .format = output_fmt, .renderable = true, .host_readable = true));
    pl_renderer renderer = pl_renderer_create(log, gpu);
    int result = 3;
    if (!input || !target || !renderer)
        goto cleanup;
    struct pl_frame src = {
        .num_planes = 1,
        .planes = {{.texture = input, .components = 4, .component_mapping = {0, 1, 2, 3}}},
        .repr = {.sys = PL_COLOR_SYSTEM_RGB, .levels = PL_COLOR_LEVELS_FULL, .alpha = PL_ALPHA_INDEPENDENT},
        .color = {.primaries = PL_COLOR_PRIM_BT_709, .transfer = PL_COLOR_TRC_SCRGB,
                  .hdr = {.min_luma = 0, .max_luma = 1000}},
    };
    struct pl_frame dst = {
        .num_planes = 1,
        .planes = {{.texture = target, .components = 4, .component_mapping = {0, 1, 2, 3}}},
        .repr = {.sys = PL_COLOR_SYSTEM_RGB, .levels = PL_COLOR_LEVELS_FULL, .alpha = PL_ALPHA_INDEPENDENT},
        .color = pl_color_space_srgb,
    };
    dst.color.hdr.min_luma = 0;
    dst.color.hdr.max_luma = 100;
    struct pl_color_map_params color = pl_color_map_default_params;
    color.tone_mapping_function = &pl_tone_map_bt2390;
    struct pl_render_params params = pl_render_default_params;
    params.color_map_params = &color;
    params.peak_detect_params = NULL;
    params.dither_params = NULL;
    // 重复渲染覆盖着色器复用和资源清理；不通过窗口、交换链或桌面采集验证。
    for (int repeat = 0; repeat < 3; ++repeat) {
        memset(output, 0, sizeof(output));
        if (!pl_render_image(renderer, &src, &dst, &params) ||
            !pl_tex_download(gpu, pl_tex_transfer_params(.tex = target, .ptr = output)))
            goto cleanup;
        int previous = -1;
        for (int band = 0; band < 5; ++band) {
            int x = (2 * band + 1) * W / 10;
            const uint8_t *pixel = output + ((H / 4) * W + x) * 4;
            printf("SDR band %d: %u %u %u %u\n", band, pixel[0], pixel[1], pixel[2], pixel[3]);
            if (pixel[0] <= previous || pixel[3] < 254 ||
                abs((int)pixel[0] - pixel[1]) > 2 || abs((int)pixel[0] - pixel[2]) > 2 ||
                (band == 0 && pixel[0] > 2) || (band == 2 && pixel[0] >= 250))
                goto cleanup;
            previous = pixel[0];
        }
        for (int channel = 0; channel < 3; ++channel) {
            int x = (2 * channel + 1) * W / 6;
            const uint8_t *pixel = output + ((H * 3 / 4) * W + x) * 4;
            printf("SDR primary %d: %u %u %u %u\n", channel, pixel[0], pixel[1], pixel[2], pixel[3]);
            if (pixel[3] < 254 || pixel[channel] < 100 ||
                pixel[channel] <= pixel[(channel + 1) % 3] + 40 ||
                pixel[channel] <= pixel[(channel + 2) % 3] + 40)
                goto cleanup;
        }
    }
    puts("FP16 scRGB to SDR synthetic render passed");
    result = 0;
cleanup:
    pl_renderer_destroy(&renderer);
    pl_tex_destroy(gpu, &input);
    pl_tex_destroy(gpu, &target);
    return result;
}
