//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"

int tv_encode(tv_encoder* e, tv_i420 f, int keyframe, int64_t timestamp, tv_output* out) {
    if (!out) return TV_INVALID;
    *out={};
    if (!e || !e->codec || !tv_i420_valid(f) || f.width!=e->config.width || f.height!=e->config.height || timestamp < 0) return TV_INVALID;
    if (e->unusable) return TV_UNUSABLE;
    if (f.u.stride != f.v.stride) {
        // OpenH264 的预处理共用 U 步长读取两个色度平面；仅此情况整理为紧密缓冲。
        auto packed=tv_buffer(e->source,f.width,f.height);
        if (libyuv::I420Copy(f.y.data,f.y.stride,f.u.data,f.u.stride,f.v.data,f.v.stride,
                            packed.y.data,packed.y.stride,packed.u.data,packed.u.stride,
                            packed.v.data,packed.v.stride,f.width,f.height)) return TV_FAILED;
        f=packed;
    }
    SSourcePicture picture{};
    picture.iColorFormat=videoFormatI420; picture.iPicWidth=f.width; picture.iPicHeight=f.height;
    picture.iStride[0]=f.y.stride; picture.iStride[1]=f.u.stride; picture.iStride[2]=f.v.stride;
    picture.pData[0]=f.y.data; picture.pData[1]=f.u.data; picture.pData[2]=f.v.data;
    picture.uiTimeStamp=timestamp;
    if (keyframe && e->codec->ForceIntraFrame(true)) return TV_FAILED;
    SFrameBSInfo frame{};
    if (e->codec->EncodeFrame(&picture,&frame)) return TV_FAILED;
    e->output.clear();
    if (frame.eFrameType==videoFrameTypeSkip) { out->skipped=1; return TV_OK; }
    if (frame.iLayerNum < 0 || frame.iLayerNum > MAX_LAYER_NUM_OF_FRAME) return TV_FAILED;
    for (int i=0;i<frame.iLayerNum;i++) {
        const auto& layer=frame.sLayerInfo[i];
        if (layer.iNalCount < 0 || layer.iNalCount > MAX_NAL_UNITS_IN_LAYER || !layer.pNalLengthInByte || !layer.pBsBuf) return TV_FAILED;
        size_t length=0;
        for (int j=0;j<layer.iNalCount;j++) {
            int n=layer.pNalLengthInByte[j];
            if (n < 0 || size_t(n) > 4*1024*1024-length) return TV_FAILED;
            length+=size_t(n);
        }
        if (length > 4*1024*1024-e->output.size()) return TV_FAILED;
        e->output.insert(e->output.end(),layer.pBsBuf,layer.pBsBuf+length);
    }
    if (e->output.empty()) return TV_FAILED;
    out->data=e->output.data(); out->length=int(e->output.size());
    out->keyframe=frame.eFrameType==videoFrameTypeIDR;
    return TV_OK;
}
extern "C" int tv_encode_i420(tv_encoder* e, tv_i420 f, int keyframe, int64_t timestamp, tv_output* out) {
    if (out) *out={};
    try { return tv_encode(e,f,keyframe,timestamp,out); } catch (...) { return TV_FAILED; }
}
extern "C" int tv_encode_bgra(tv_encoder* e, const uint8_t* pixels, size_t length, int width, int height, int stride, int keyframe, int64_t timestamp, tv_output* out) {
    if (out) *out={};
    if (!e || !out || !tv_size(width,height) || !tv_plane_valid({const_cast<uint8_t*>(pixels),length,stride},width*4,height)) return TV_INVALID;
    if (e->unusable) return TV_UNUSABLE;
    try {
        auto source=tv_buffer(e->source,width,height);
        int status=TV_OK;
        if (e->config.matrix==709) {
            status=libyuv::ARGBToI420Matrix(pixels,stride,source.y.data,source.y.stride,
                source.u.data,source.u.stride,source.v.data,source.v.stride,
                &libyuv::kArgbH709Constants,width,height) ? TV_FAILED : TV_OK;
        } else status=tv_convert(pixels,length,width,height,stride,source);
        if (status!=TV_OK) return status;
        if (width==e->config.width && height==e->config.height) return tv_encode(e,source,keyframe,timestamp,out);
        auto scaled=tv_buffer(e->scaled,e->config.width,e->config.height);
        status=tv_scale(source,scaled);
        return status==TV_OK ? tv_encode(e,scaled,keyframe,timestamp,out) : status;
    } catch (...) { return TV_FAILED; }
}
