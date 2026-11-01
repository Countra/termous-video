#pragma once
#include <stdint.h>
#ifdef _WIN32
#include <windows.h>
static uint64_t tv_color_now(void) {
  LARGE_INTEGER value, frequency;
  QueryPerformanceCounter(&value);
  QueryPerformanceFrequency(&frequency);
  return (uint64_t)((double)value.QuadPart * 1e9 / (double)frequency.QuadPart);
}
#else
#include <time.h>
static uint64_t tv_color_now(void) {
  struct timespec value;
  clock_gettime(CLOCK_MONOTONIC, &value);
  return (uint64_t)value.tv_sec * 1000000000 + value.tv_nsec;
}
#endif
