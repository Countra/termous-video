# Video dependency SDK: linux/amd64

Separate private static archives: libtermous_video_x264.a, libtermous_video_yuv.a and libtermous_video_openh264.a.

Include termous_video_symbols.h before third-party headers. Headers are in include/.

x264 165-0480cb0 provides 8-bit 4:2:0 progressive encoding only; libyuv excludes JPEG. OpenH264 2.6.0 includes encoding and decoding; SDK tests use its decoder to verify x264 output. All three libraries retain architecture-specific SIMD paths. Encoding with x264 and libyuv does not require linking OpenH264.

The placebo/ component contains libplacebo and its static backend dependencies with original symbols. See placebo/link.json for link order and placebo/manifest.json for rendering results.

See the repository 3rd/README.md for compiler and linker requirements. This SDK does not provide a production Go API.
