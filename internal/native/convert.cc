//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"

bool tv_size(int width, int height) {
    return width > 0 && height > 0 && uint64_t(width) * uint64_t(height) <= 16 * 1024 * 1024;
}
bool tv_plane_valid(tv_plane plane, int width, int height) {
    return plane.data && plane.stride >= width && plane.length >= uint64_t(height - 1) * plane.stride + width;
}
bool tv_i420_valid(tv_i420 f) {
    return tv_size(f.width, f.height) && tv_plane_valid(f.y, f.width, f.height)
        && tv_plane_valid(f.u, (f.width+1)/2, (f.height+1)/2)
        && tv_plane_valid(f.v, (f.width+1)/2, (f.height+1)/2);
}
tv_i420 tv_buffer(std::vector<uint8_t>& data, int width, int height) {
    const size_t y = size_t(width)*height, c = size_t((width+1)/2)*((height+1)/2);
    data.resize(y+2*c);
    return {{data.data(),y,width}, {data.data()+y,c,(width+1)/2}, {data.data()+y+c,c,(width+1)/2}, width,height};
}
extern "C" int tv_convert(const uint8_t* pixels, size_t length, int width, int height, int stride, tv_i420 out) {
    if (!tv_size(width,height) || !tv_plane_valid({const_cast<uint8_t*>(pixels),length,stride},width*4,height)
        || !tv_i420_valid(out) || out.width != width || out.height != height) return TV_INVALID;
    try {
        // libyuv 的 ARGB 使用寄存器命名；本项目小端平台内存排列为 BGRA。
        return libyuv::ARGBToI420(pixels,stride,out.y.data,out.y.stride,out.u.data,out.u.stride,out.v.data,out.v.stride,width,height) ? TV_FAILED : TV_OK;
    } catch (...) { return TV_FAILED; }
}
extern "C" int tv_scale(tv_i420 src, tv_i420 out) {
    if (!tv_i420_valid(src) || !tv_i420_valid(out)) return TV_INVALID;
    try {
        return libyuv::I420Scale(src.y.data,src.y.stride,src.u.data,src.u.stride,src.v.data,src.v.stride,src.width,src.height,
            out.y.data,out.y.stride,out.u.data,out.u.stride,out.v.data,out.v.stride,out.width,out.height,libyuv::kFilterBilinear) ? TV_FAILED : TV_OK;
    } catch (...) { return TV_FAILED; }
}
