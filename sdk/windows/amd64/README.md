# Video dependency SDK: windows/amd64

Separate private static archives: libtermous_video_x264.a and libtermous_video_yuv.a.

Include termous_video_symbols.h before third-party headers. Headers are in include/.

x264 165-0480cb0 provides 8-bit 4:2:0 progressive encoding only; libyuv excludes JPEG. Both libraries retain architecture-specific SIMD paths.

The placebo/ component contains libplacebo and its static backend dependencies with original symbols. See placebo/link.json for link order and placebo/manifest.json for rendering results.

See the repository 3rd/README.md for compiler and linker requirements. This SDK does not provide a production Go API.
