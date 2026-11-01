//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "bridge.h"
#include <termous_video_symbols.h>
#include <wels/codec_api.h>
#include <memory>

extern "C" int tv_test_decode(const uint8_t* data,int length,int* width,int* height,int* yuv) {
    try {
        ISVCDecoder* raw=nullptr;
        if (WelsCreateDecoder(&raw) || !raw) return TV_FAILED;
        auto release=[](ISVCDecoder* p){p->Uninitialize();WelsDestroyDecoder(p);};
        std::unique_ptr<ISVCDecoder,decltype(release)> decoder(raw,release);
        SDecodingParam params{};params.sVideoProperty.eVideoBsType=VIDEO_BITSTREAM_AVC;params.eEcActiveIdc=ERROR_CON_DISABLE;
        if (decoder->Initialize(&params)) return TV_FAILED;
        int threads=0;
        if (decoder->SetOption(DECODER_OPTION_NUM_OF_THREADS,&threads)) return TV_FAILED;
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
extern "C" int tv_test_decode_sequence(const uint8_t* data,int total,const int* lengths,int count,int width,int height,int* samples) {
    if (!data || !lengths || !samples || count<1 || count>256 || total<1 || width<1 || height<1) return TV_INVALID;
    try {
        ISVCDecoder* raw=nullptr;
        if (WelsCreateDecoder(&raw) || !raw) return TV_FAILED;
        auto release=[](ISVCDecoder* p){p->Uninitialize();WelsDestroyDecoder(p);};
        std::unique_ptr<ISVCDecoder,decltype(release)> decoder(raw,release);
        SDecodingParam params{};params.sVideoProperty.eVideoBsType=VIDEO_BITSTREAM_AVC;params.eEcActiveIdc=ERROR_CON_DISABLE;
        if (decoder->Initialize(&params)) return TV_FAILED;
        int threads=0;
        if (decoder->SetOption(DECODER_OPTION_NUM_OF_THREADS,&threads)) return TV_FAILED;
        int offset=0;
        for (int i=0;i<count;++i) {
            if (lengths[i]<1 || lengths[i]>total-offset) return TV_INVALID;
            unsigned char* planes[3]{};SBufferInfo info{};
            info.uiInBsTimeStamp=uint64_t(i+1);
            if (decoder->DecodeFrameNoDelay(data+offset,lengths[i],planes,&info)!=dsErrorFree || info.iBufferStatus!=1 ||
                !planes[0] || !planes[1] || !planes[2] || info.uiOutYuvTimeStamp!=uint64_t(i+1) ||
                info.UsrData.sSystemBuffer.iStride[0]<width || info.UsrData.sSystemBuffer.iStride[1]<(width+1)/2 ||
                info.UsrData.sSystemBuffer.iWidth!=width || info.UsrData.sSystemBuffer.iHeight!=height) return TV_FAILED;
            const auto& layout=info.UsrData.sSystemBuffer;
            samples[i*3]=planes[0][(height-1)*layout.iStride[0]];
            samples[i*3+1]=planes[1][((height-1)/2)*layout.iStride[1]];
            samples[i*3+2]=planes[2][((height-1)/2)*layout.iStride[1]];
            offset+=lengths[i];
        }
        int end=1, remaining=-1;
        if (decoder->SetOption(DECODER_OPTION_END_OF_STREAM,&end) ||
            decoder->GetOption(DECODER_OPTION_NUM_OF_FRAMES_REMAINING_IN_BUFFER,&remaining) || remaining!=0) return TV_FAILED;
        unsigned char* planes[3]{};SBufferInfo info{};
        if (decoder->FlushFrame(planes,&info)!=dsErrorFree || info.iBufferStatus) return TV_FAILED;
        return offset==total ? TV_OK : TV_INVALID;
    } catch (...) { return TV_FAILED; }
}
