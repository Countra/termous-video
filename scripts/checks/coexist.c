#include <stdint.h>
#include <stdio.h>

int original_smoke(void);
int private_smoke(void);
void original_binding(uintptr_t entries[3]);
void private_binding(uintptr_t entries[3]);

int main(void) {
    uintptr_t original[3] = {0}, private_entries[3] = {0};
    original_binding(original);
    private_binding(private_entries);
    for (int index = 0; index < 3; ++index) {
        if (!original[index] || !private_entries[index] || original[index] == private_entries[index]) {
            fprintf(stderr, "Private and original SDK resolved to the same dependency: entry=%d\n", index);
            return 100;
        }
    }
    int result = original_smoke();
    if (!result) result = private_smoke();
    if (result) fprintf(stderr, "Combined SDK check failed at stage %d\n", result);
    return result;
}
