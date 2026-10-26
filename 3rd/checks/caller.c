#include <stdio.h>

int video_sdk_smoke(void);

int main(void) {
  int result = video_sdk_smoke();
  if (result) fprintf(stderr, "Synthetic video check failed at stage %d\n", result);
  return result;
}
