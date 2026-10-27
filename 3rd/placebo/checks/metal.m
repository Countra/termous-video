#import <Metal/Metal.h>
#include "check.h"

int placebo_metal_available(void)
{
    // 独立探测系统 Metal，不能把 MoltenVK 初始化错误当作 runner 缺少 GPU。
    @autoreleasepool {
        id<MTLDevice> device = MTLCreateSystemDefaultDevice();
        int available = device != nil;
        [device release];
        return available;
    }
}
