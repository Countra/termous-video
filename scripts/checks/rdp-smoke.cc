// 只消费调用者提供的 RDP SDK；video 的编译与发布不依赖 OpenH264。
#include <wels/codec_api.h>
#include <libyuv.h>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <vector>

extern "C" int video_sdk_smoke() {
  try {
    constexpr int source_size = 128, size = 64;
    std::vector<uint8_t> bgra(source_size * source_size * 4);
    for (int y = 0; y < source_size; ++y) {
      for (int x = 0; x < source_size; ++x) {
        auto* p = &bgra[(y * source_size + x) * 4];
        p[0] = x < 64 ? 200 : 40;
        p[1] = y < 64 ? 180 : 20;
        p[2] = 80;
        p[3] = 255;
      }
    }
    std::vector<uint8_t> source(source_size * source_size * 3 / 2);
    auto* sy = source.data();
    auto* su = sy + source_size * source_size;
    auto* sv = su + source_size * source_size / 4;
    if (libyuv::ARGBToI420(bgra.data(), source_size * 4, sy, source_size, su,
                         source_size / 2, sv, source_size / 2, source_size, source_size)) return 1;
    std::vector<uint8_t> pixels(size * size * 3 / 2);
    auto* y = pixels.data();
    auto* u = y + size * size;
    auto* v = u + size * size / 4;
    if (libyuv::I420Scale(sy, source_size, su, source_size / 2, sv, source_size / 2,
                         source_size, source_size, y, size, u, size / 2, v, size / 2,
                         size, size, libyuv::kFilterBilinear)) return 2;
    ISVCEncoder* raw_encoder = nullptr;
    if (WelsCreateSVCEncoder(&raw_encoder) || !raw_encoder) return 3;
    auto free_encoder = [](ISVCEncoder* p) { p->Uninitialize(); WelsDestroySVCEncoder(p); };
    std::unique_ptr<ISVCEncoder, decltype(free_encoder)> encoder(raw_encoder, free_encoder);
    int quiet = WELS_LOG_QUIET;
    if (encoder->SetOption(ENCODER_OPTION_TRACE_LEVEL, &quiet)) return 4;
    SEncParamBase params{};
    params.iUsageType = SCREEN_CONTENT_REAL_TIME;
    params.iPicWidth = size;
    params.iPicHeight = size;
    params.iTargetBitrate = 300000;
    params.iRCMode = RC_BITRATE_MODE;
    params.fMaxFrameRate = 30;
    if (encoder->Initialize(&params)) return 5;
    SSourcePicture picture{};
    picture.iColorFormat = videoFormatI420;
    picture.iPicWidth = size;
    picture.iPicHeight = size;
    picture.iStride[0] = size;
    picture.iStride[1] = picture.iStride[2] = size / 2;
    picture.pData[0] = y;
    picture.pData[1] = u;
    picture.pData[2] = v;
    SFrameBSInfo encoded{};
    if (encoder->EncodeFrame(&picture, &encoded) || encoded.eFrameType != videoFrameTypeIDR) return 6;
    std::vector<uint8_t> bitstream;
    for (int layer = 0; layer < encoded.iLayerNum; ++layer) {
      const auto& info = encoded.sLayerInfo[layer];
      int length = 0;
      for (int nal = 0; nal < info.iNalCount; ++nal) length += info.pNalLengthInByte[nal];
      if (length <= 0) return 7;
      bitstream.insert(bitstream.end(), info.pBsBuf, info.pBsBuf + length);
    }
    if (bitstream.empty()) return 8;
    ISVCDecoder* raw_decoder = nullptr;
    if (WelsCreateDecoder(&raw_decoder) || !raw_decoder) return 9;
    auto free_decoder = [](ISVCDecoder* p) { p->Uninitialize(); WelsDestroyDecoder(p); };
    std::unique_ptr<ISVCDecoder, decltype(free_decoder)> decoder(raw_decoder, free_decoder);
    SDecodingParam decoding{};
    decoding.sVideoProperty.eVideoBsType = VIDEO_BITSTREAM_AVC;
    if (decoder->Initialize(&decoding)) return 10;
    unsigned char* planes[3]{};
    SBufferInfo frame{};
    if (decoder->DecodeFrameNoDelay(bitstream.data(), static_cast<int>(bitstream.size()), planes, &frame)
        != dsErrorFree) return 11;
    if (frame.iBufferStatus != 1 || frame.UsrData.sSystemBuffer.iWidth != size
        || frame.UsrData.sSystemBuffer.iHeight != size || !planes[0]) return 12;
    // 验证实际解码数据，避免只创建对象就把链接成功误报为功能通过。
    const int stride = frame.UsrData.sSystemBuffer.iStride[0];
    if (planes[0][8 * stride + 8] <= planes[0][48 * stride + 48]) return 13;
    return 0;
  } catch (...) {
    std::fputs("Synthetic video check raised an exception\n", stderr);
    return 99;
  }
}
