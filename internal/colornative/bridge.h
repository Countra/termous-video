#pragma once
#include <stddef.h>
#include <stdint.h>
typedef struct tv_color tv_color;
tv_color *tv_color_create(int software);
void tv_color_destroy(tv_color *state);
const char *tv_color_backend(tv_color *state);
int tv_color_failed(tv_color *state);
int tv_color_process(tv_color *state, const uint8_t *input, size_t input_length,
                     int width, int height, int stride, float peak,
                     uint8_t *output, size_t output_length, int output_stride);
