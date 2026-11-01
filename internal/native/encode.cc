//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"
#include <limits>
#include <chrono>

using video_clock = std::chrono::steady_clock;

static int unusable(tv_encoder* e) { e->unusable=true; return TV_UNUSABLE; }

int tv_encode(tv_encoder* e, tv_i420 f, tv_options options, tv_output* out) {
    const auto started = options.measure_stages ? video_clock::now() : video_clock::time_point{};
    if (!out) return TV_INVALID;
    *out={};
    if (!e || !e->codec || !tv_i420_valid(f) || f.width!=e->config.width || f.height!=e->config.height || options.timestamp<0) return TV_INVALID;
    if (e->unusable) return TV_UNUSABLE;
    if (e->sequence==std::numeric_limits<int64_t>::max()) return unusable(e);
    tv_config candidate{};
    const int status=tv_prepare_rate(e,options,candidate);
    if (status!=TV_OK) return status;
    // 重配与编码属于同一事务；进入编码后失败不能假定参考链或码率已恢复。
    try {
#ifdef TERMOUS_VIDEO_FIXTURE
        if (e->fault==2) { e->fault=0; return unusable(e); }
#endif
        x264_picture_t input{}, output{};
        x264_picture_init(&input);
        input.img.i_csp=X264_CSP_I420; input.img.i_plane=3;
        input.img.i_stride[0]=f.y.stride; input.img.i_stride[1]=f.u.stride; input.img.i_stride[2]=f.v.stride;
        input.img.plane[0]=f.y.data; input.img.plane[1]=f.u.data; input.img.plane[2]=f.v.data;
        input.i_pts=e->sequence;
        input.i_type=options.keyframe ? X264_TYPE_IDR : X264_TYPE_AUTO;
        x264_nal_t* nals=nullptr;
        int count=0;
        const int bytes=x264_encoder_encode(e->codec,&nals,&count,&input,&output);
        if (bytes<=0 || bytes>4*1024*1024 || !nals || count<1 || count>bytes/4 ||
            x264_encoder_delayed_frames(e->codec)!=0 || output.i_pts!=e->sequence || output.i_dts!=e->sequence ||
            !tv_parameters_match(e->codec,candidate)) return unusable(e);
#ifdef TERMOUS_VIDEO_FIXTURE
        if (e->fault==3) { e->fault=0; return unusable(e); }
#endif
        int offset=0;
        bool idr=false, sps=false, pps=false;
        const uint8_t* data=nals[0].p_payload;
        if (!data) return unusable(e);
        for (int i=0;i<count;++i) {
            const auto& n=nals[i];
            const int prefix=n.b_long_startcode ? 4 : 3;
            if (n.i_payload<=prefix || n.i_payload>bytes-offset || n.p_payload!=data+offset) return unusable(e);
            for (int j=0;j<prefix-1;++j) if (n.p_payload[j]!=0) return unusable(e);
            if (n.p_payload[prefix-1]!=1 || (n.p_payload[prefix]&31)!=n.i_type) return unusable(e);
            idr=idr || n.i_type==NAL_SLICE_IDR;
            sps=sps || n.i_type==NAL_SPS; pps=pps || n.i_type==NAL_PPS;
            offset+=n.i_payload;
        }
        if (offset!=bytes || (idr && (!sps || !pps)) || (options.keyframe && !idr)) return unusable(e);
        e->config=candidate;
        ++e->sequence;
        // x264 保证 NAL 连续；Go 在释放实例锁前复制，原生不再拼接第二份输出。
        out->data=data; out->length=bytes; out->keyframe=idr;
        // x264 的 8 位全局率控 QP 可到 69；不是码流切片 QP、宏块均值或画质评分。
        if (output.i_qpplus1>=1 && output.i_qpplus1<=70) out->qp_plus_one=output.i_qpplus1;
        if (options.measure_stages) out->encoding_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(video_clock::now()-started).count();
        return TV_OK;
    } catch (...) { return unusable(e); }
}

extern "C" int tv_encode_i420(tv_encoder* e, tv_i420 f, tv_options options, tv_output* out) {
    if (out) *out={};
    try { return tv_encode(e,f,options,out); } catch (...) { return e ? unusable(e) : TV_FAILED; }
}

extern "C" int tv_encode_bgra(tv_encoder* e, const uint8_t* pixels, size_t length, int width, int height, int stride, tv_options options, tv_output* out) {
    if (out) *out={};
    if (!e || !out || !tv_size(width,height) || !tv_plane_valid({const_cast<uint8_t*>(pixels),length,stride},width*4,height) || options.timestamp<0) return TV_INVALID;
    if (e->unusable) return TV_UNUSABLE;
    // 全部像素准备在提交原生重配之前完成，转换失败不留下待应用配置。
    const auto started = options.measure_stages ? video_clock::now() : video_clock::time_point{};
    tv_i420 prepared{};
    try {
        auto source=tv_buffer(e->source,width,height);
        int status=TV_OK;
        if (e->config.matrix==709) {
            status=libyuv::ARGBToI420Matrix(pixels,stride,source.y.data,source.y.stride,
                source.u.data,source.u.stride,source.v.data,source.v.stride,
                &libyuv::kArgbH709Constants,width,height) ? TV_FAILED : TV_OK;
        } else status=tv_convert(pixels,length,width,height,stride,source);
        if (status!=TV_OK) return status;
        prepared=source;
        if (width!=e->config.width || height!=e->config.height) {
            prepared=tv_buffer(e->scaled,e->config.width,e->config.height);
            status=tv_scale(source,prepared);
            if (status!=TV_OK) return status;
        }
    } catch (...) { return TV_FAILED; }
    const auto converted = options.measure_stages ? video_clock::now() : video_clock::time_point{};
    const int result=tv_encode(e,prepared,options,out);
    if (result==TV_OK && options.measure_stages) out->conversion_ns=std::chrono::duration_cast<std::chrono::nanoseconds>(converted-started).count();
    return result;
}
