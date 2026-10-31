#include "codec_check.h"

#include <cstdio>
#include <memory>
#include <wels/codec_api.h>
#include <wels/codec_ver.h>

namespace {
struct Decoder {
  ISVCDecoder* value = nullptr;
  bool initialized = false;
  int frames = 0;

  ~Decoder() {
    if (value) {
      if (initialized) value->Uninitialize();
      WelsDestroyDecoder(value);
    }
  }

  int initialize() {
    if (WelsCreateDecoder(&value) || !value) return 20;
    int quiet = WELS_LOG_QUIET;
    // OpenH264 的 0 表示同步单线程；1 会启用异步工作线程并改变输出时序。
    int threads = 0;
    if (value->SetOption(DECODER_OPTION_TRACE_LEVEL, &quiet) ||
        value->SetOption(DECODER_OPTION_NUM_OF_THREADS, &threads)) return 21;
    SDecodingParam parameters{};
    parameters.sVideoProperty.eVideoBsType = VIDEO_BITSTREAM_AVC;
    parameters.eEcActiveIdc = ERROR_CON_DISABLE;
    if (value->Initialize(&parameters)) return 21;
    initialized = true;
    int applied_threads = -1, concealment = -1;
    if (value->GetOption(DECODER_OPTION_NUM_OF_THREADS, &applied_threads) || applied_threads != 0 ||
        value->GetOption(DECODER_OPTION_ERROR_CON_IDC, &concealment) || concealment != ERROR_CON_DISABLE) return 21;
    return 0;
  }

  int decode(const uint8_t* bytes, int length, int frame) {
    if (!bytes || length <= 0 || frame != frames) return 22;
    unsigned char* planes[3]{};
    SBufferInfo info{};
    const auto timestamp = static_cast<unsigned long long>(1000 + frame * 17);
    info.uiInBsTimeStamp = timestamp;
    const DECODING_STATE state = value->DecodeFrameNoDelay(bytes, length, planes, &info);
    if (state != dsErrorFree || info.iBufferStatus != 1) {
      std::fprintf(stderr, "OpenH264 decode failed: frame=%d state=0x%x buffer_status=%d bytes=%d\n",
                   frame, static_cast<unsigned int>(state), info.iBufferStatus, length);
      return 22;
    }
    const auto& system = info.UsrData.sSystemBuffer;
    if (info.uiOutYuvTimeStamp != timestamp || system.iWidth != kFrameWidth ||
        system.iHeight != kFrameHeight || system.iFormat != videoFormatI420) {
      std::fprintf(stderr, "Decoded metadata mismatch: frame=%d timestamp=%llu expected=%llu size=%dx%d format=%d\n",
                   frame, info.uiOutYuvTimeStamp, timestamp, system.iWidth, system.iHeight, system.iFormat);
      return 23;
    }
    const int strides[3] = {system.iStride[0], system.iStride[1], system.iStride[1]};
    const int error = check_pixels(planes, strides, frame);
    if (error) return error;
    ++frames;
    return 0;
  }

  int finish() {
    int eos = 1, remaining = -1;
    if (frames != kFrameCount || value->SetOption(DECODER_OPTION_END_OF_STREAM, &eos) ||
        value->GetOption(DECODER_OPTION_NUM_OF_FRAMES_REMAINING_IN_BUFFER, &remaining) || remaining != 0)
      return 26;
    unsigned char* planes[3]{};
    SBufferInfo info{};
    if (value->FlushFrame(planes, &info) != dsErrorFree || info.iBufferStatus != 0) return 26;
    const long result = value->Uninitialize();
    initialized = false;
    return result ? 27 : 0;
  }
};

int consume_frame(const uint8_t* bytes, int length, int frame, void* context) {
  return static_cast<Decoder*>(context)->decode(bytes, length, frame);
}
}

int decode_sequence(int threads) {
  Decoder decoder;
  int error = decoder.initialize();
  if (!error) error = encode_sequence(threads, consume_frame, &decoder);
  return error ? error : decoder.finish();
}

int check_openh264_api() {
  const auto version = WelsGetCodecVersion();
  OpenH264Version extended{};
  WelsGetCodecVersionEx(&extended);
  if (version.uMajor != OPENH264_MAJOR || version.uMinor != OPENH264_MINOR ||
      version.uRevision != OPENH264_REVISION || version.uReserved != OPENH264_RESERVED ||
      extended.uMajor != version.uMajor || extended.uMinor != version.uMinor ||
      extended.uRevision != version.uRevision || extended.uReserved != version.uReserved) return 30;
  ISVCEncoder* raw = nullptr;
  if (WelsCreateSVCEncoder(&raw) || !raw) return 31;
  std::unique_ptr<ISVCEncoder, decltype(&WelsDestroySVCEncoder)> encoder(raw, WelsDestroySVCEncoder);
  int quiet = WELS_LOG_QUIET;
  if (encoder->SetOption(ENCODER_OPTION_TRACE_LEVEL, &quiet)) return 32;
  SEncParamBase parameters{};
  parameters.iUsageType = SCREEN_CONTENT_REAL_TIME;
  parameters.iPicWidth = parameters.iPicHeight = 64;
  parameters.iTargetBitrate = 300000;
  parameters.iRCMode = RC_BITRATE_MODE;
  parameters.fMaxFrameRate = 30;
  if (encoder->Initialize(&parameters)) return 33;
  return encoder->Uninitialize() ? 34 : 0;
}
