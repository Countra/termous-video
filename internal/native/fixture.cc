//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"
#include <memory>

// 故障只注入测试对象，不为生产编码器增加可变测试开关。
class FaultCodec final : public ISVCEncoder {
public:
    int calls=0, bitrate=500000, fps=15, fail=2;
    bool permanent=false;
    int Initialize(const SEncParamBase*) override { return 0; }
    int InitializeExt(const SEncParamExt*) override { return 0; }
    int GetDefaultParams(SEncParamExt*) override { return 0; }
    int Uninitialize() override { return 0; }
    int EncodeFrame(const SSourcePicture*,SFrameBSInfo*) override { return 0; }
    int EncodeParameterSets(SFrameBSInfo*) override { return 0; }
    int ForceIntraFrame(bool,int) override { return 0; }
    int GetOption(ENCODER_OPTION,void*) override { return 0; }
    int SetOption(ENCODER_OPTION option,void* value) override {
        calls++;
        if (calls==fail || (permanent && calls>=fail)) return -1;
        if (option==ENCODER_OPTION_BITRATE) bitrate=static_cast<SBitrateInfo*>(value)->iBitrate;
        if (option==ENCODER_OPTION_FRAME_RATE) fps=int(*static_cast<float*>(value));
        return 0;
    }
};
extern "C" int tv_test_rate() {
    FaultCodec codec;
    tv_encoder e;
    e.codec=&codec;e.config={320,180,500000,15,31};
    int result=tv_rate(&e,1000000,30);
    bool restored=result==TV_FAILED && codec.bitrate==500000 && codec.fps==15 && !e.unusable;
    codec.calls=0;codec.permanent=true;
    result=tv_rate(&e,1000000,30);
    bool unusable=result==TV_UNUSABLE && e.unusable && tv_rate(&e,500000,15)==TV_UNUSABLE;
    e.codec=nullptr;
    return restored && unusable ? 0 : 1;
}
extern "C" int tv_test_decode(const uint8_t* data,int length,int* width,int* height,int* yuv) {
    try {
        ISVCDecoder* raw=nullptr;
        if (WelsCreateDecoder(&raw) || !raw) return TV_FAILED;
        auto release=[](ISVCDecoder* p){p->Uninitialize();WelsDestroyDecoder(p);};
        std::unique_ptr<ISVCDecoder,decltype(release)> decoder(raw,release);
        SDecodingParam params{};params.sVideoProperty.eVideoBsType=VIDEO_BITSTREAM_AVC;
        if (decoder->Initialize(&params)) return TV_FAILED;
        unsigned char* planes[3]{};SBufferInfo info{};
        if (decoder->DecodeFrameNoDelay(data,length,planes,&info)!=dsErrorFree || info.iBufferStatus!=1 || !planes[0] || !planes[1] || !planes[2]) return TV_FAILED;
        const auto& layout=info.UsrData.sSystemBuffer;
        *width=layout.iWidth;*height=layout.iHeight;
        if (*width < 1 || *height < 1 || layout.iStride[0] < *width || layout.iStride[1] < (*width+1)/2) return TV_FAILED;
        // 采样末行，避免只验证首行而漏掉输入平面的步长错误。
        yuv[0]=planes[0][(*height-1)*layout.iStride[0]];
        yuv[1]=planes[1][((*height-1)/2)*layout.iStride[1]];
        yuv[2]=planes[2][((*height-1)/2)*layout.iStride[1]];
        return TV_OK;
    } catch (...) { return TV_FAILED; }
}

// 使用同一解码器逐个提交完整访问单元，验证速率更新后的参考链而非孤立关键帧。
extern "C" int tv_test_decode_sequence(const uint8_t* data,int total,const int* lengths,int count,int width,int height) {
    if (!data || !lengths || count<1 || count>256 || total<1) return TV_INVALID;
    try {
        ISVCDecoder* raw=nullptr;
        if (WelsCreateDecoder(&raw) || !raw) return TV_FAILED;
        auto release=[](ISVCDecoder* p){p->Uninitialize();WelsDestroyDecoder(p);};
        std::unique_ptr<ISVCDecoder,decltype(release)> decoder(raw,release);
        SDecodingParam params{};params.sVideoProperty.eVideoBsType=VIDEO_BITSTREAM_AVC;
        if (decoder->Initialize(&params)) return TV_FAILED;
        int offset=0;
        for (int i=0;i<count;++i) {
            if (lengths[i]<1 || lengths[i]>total-offset) return TV_INVALID;
            unsigned char* planes[3]{};SBufferInfo info{};
            if (decoder->DecodeFrameNoDelay(data+offset,lengths[i],planes,&info)!=dsErrorFree || info.iBufferStatus!=1 ||
                info.UsrData.sSystemBuffer.iWidth!=width || info.UsrData.sSystemBuffer.iHeight!=height) return TV_FAILED;
            offset+=lengths[i];
        }
        return offset==total ? TV_OK : TV_INVALID;
    } catch (...) { return TV_FAILED; }
}
