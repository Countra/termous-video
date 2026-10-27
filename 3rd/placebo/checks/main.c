#include "check.h"
#include <string.h>

int main(int argc, char **argv)
{
    int mode = 1;
    if (argc == 2) {
        if (!strcmp(argv[1], "--api-only")) mode = 0;
        else if (!strcmp(argv[1], "--software")) mode = 2;
        else if (!strcmp(argv[1], "--hardware")) mode = 3;
        else return 64;
    } else if (argc != 1) {
        return 64;
    }
    return placebo_check(mode);
}
