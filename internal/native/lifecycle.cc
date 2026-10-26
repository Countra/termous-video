//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

#include "encoder_state.h"
#include <memory>

tv_encoder::~tv_encoder() {
    if (codec) {
        // C ABI 不允许异常逃逸；析构仍须尝试释放 OpenH264 对象。
        try { codec->Uninitialize(); } catch (...) {}
        try { WelsDestroySVCEncoder(codec); } catch (...) {}
    }
}
extern "C" void tv_destroy(tv_encoder* encoder) { delete encoder; }

extern "C" int tv_create(tv_config c, tv_encoder** output) {
    if (!output) return TV_INVALID;
    *output=nullptr;
    if (c.width < 16 || c.height < 16 || c.width > 1920 || c.height > 1080 || c.width%2 || c.height%2
        || c.bitrate < 100000 || c.bitrate > 8000000 || c.fps < 1 || c.fps > 30
        || (c.level != 31 && c.level != 40) || (c.level == 31 && (c.width > 1280 || c.height > 720))) return TV_INVALID;
    try {
        auto e=std::make_unique<tv_encoder>();
        if (WelsCreateSVCEncoder(&e->codec) || !e->codec) return TV_FAILED;
        SEncParamExt p{};
        if (e->codec->GetDefaultParams(&p)) return TV_FAILED;
        p.iUsageType=SCREEN_CONTENT_REAL_TIME;
        p.iPicWidth=c.width; p.iPicHeight=c.height;
        p.iTargetBitrate=c.bitrate; p.iMaxBitrate=8000000;
        p.iRCMode=RC_BITRATE_MODE; p.fMaxFrameRate=float(c.fps);
        p.iTemporalLayerNum=1; p.iSpatialLayerNum=1;
        p.uiIntraPeriod=c.fps*2; p.bEnableFrameSkip=true;
        p.bEnableAdaptiveQuant=false; p.bEnableBackgroundDetection=false;
        p.iMultipleThreadIdc=2; p.iEntropyCodingModeFlag=0;
        auto& layer=p.sSpatialLayers[0];
        layer.iVideoWidth=c.width; layer.iVideoHeight=c.height; layer.fFrameRate=float(c.fps);
        layer.iSpatialBitrate=c.bitrate; layer.iMaxSpatialBitrate=p.iMaxBitrate;
        layer.uiProfileIdc=PRO_BASELINE; layer.uiLevelIdc=static_cast<ELevelIdc>(c.level);
        layer.sSliceArgument.uiSliceMode=SM_SINGLE_SLICE;
        if (e->codec->InitializeExt(&p)) return TV_FAILED;
        e->config=c; *output=e.release();
        return TV_OK;
    } catch (...) { return TV_FAILED; }
}
