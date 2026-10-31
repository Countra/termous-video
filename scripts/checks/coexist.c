#include <stdint.h>
#include <stdio.h>

int original_smoke(void);
int private_smoke(void);
uintptr_t original_binding(void);
uintptr_t private_binding(void);

int main(void) {
    if (original_binding() == private_binding()) {
        fputs("Private and original SDK resolved to the same libyuv implementation\n", stderr);
        return 100;
    }
    int result = original_smoke();
    if (!result) result = private_smoke();
    if (result) fprintf(stderr, "Combined SDK check failed at stage %d\n", result);
    return result;
}
