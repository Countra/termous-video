# Video dependency SDK: linux/amd64

Separate static archives: libopenh264.a and libyuv.a. Headers are in include/.

OpenH264 2.6.0 includes encoding and decoding; libyuv excludes JPEG. Both libraries retain architecture-specific SIMD paths.

See the repository 3rd/README.md for compiler and linker requirements. This SDK does not provide a production Go API.
