#include <stdint.h>
#include <stdio.h>

int original_smoke(void);
int private_smoke(void);
uintptr_t original_binding(int entry);
uintptr_t private_binding(int entry);

int main(void) {
    for (int entry = 0; entry < 2; ++entry) {
        if (original_binding(entry) == private_binding(entry)) {
            fputs("Private and original SDK resolved to the same implementation\n", stderr);
            return 100;
        }
    }
    int result = original_smoke();
    if (!result) result = private_smoke();
    if (result) fprintf(stderr, "Combined SDK check failed at stage %d\n", result);
    return result;
}
