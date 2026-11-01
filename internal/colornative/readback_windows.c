//go:build cgo && windows && amd64

#include "readback.h"
#include "timing.h"
#include <string.h>

static int make_query(ID3D11Device *device, D3D11_QUERY kind, ID3D11Query **out) {
  D3D11_QUERY_DESC desc = {.Query = kind};
  return SUCCEEDED(ID3D11Device_CreateQuery(device, &desc, out));
}

int tv_readback_create(tv_color *s) {
  struct tv_readback *r = s->readback;
  ID3D11Device *device = s->device->device;
  ID3D11Device_GetImmediateContext(device, &r->context);
  for (int i = 0; i < TV_COLOR_SLOTS; i++) {
    struct tv_readback_slot *slot = &r->slots[i];
    D3D11_TEXTURE2D_DESC desc = {.Width = r->width, .Height = r->height,
      .MipLevels = 1, .ArraySize = 1, .Format = DXGI_FORMAT_R8G8B8A8_UNORM,
      .SampleDesc = {.Count = 1}, .Usage = D3D11_USAGE_DEFAULT,
      .BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE};
    if (FAILED(ID3D11Device_CreateTexture2D(device, &desc, NULL, &slot->texture))) return 0;
    slot->output = pl_d3d11_wrap(s->gpu, pl_d3d11_wrap_params(.tex = (ID3D11Resource *)slot->texture));
    if (!slot->output) return 0;
    desc.Usage = D3D11_USAGE_STAGING; desc.BindFlags = 0; desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    if (FAILED(ID3D11Device_CreateTexture2D(device, &desc, NULL, &slot->staging)) ||
        !make_query(device, D3D11_QUERY_EVENT, &slot->event)) return 0;
    D3D11_MAPPED_SUBRESOURCE mapped;
    if (FAILED(ID3D11DeviceContext_Map(r->context, (ID3D11Resource *)slot->staging, 0, D3D11_MAP_READ, 0, &mapped))) return 0;
    int valid_pitch = mapped.RowPitch >= (size_t)r->width * 4 && mapped.RowPitch <= r->pitch;
    ID3D11DeviceContext_Unmap(r->context, (ID3D11Resource *)slot->staging, 0);
    if (!valid_pitch) return 0;
    if (r->measure) {
      // 诊断资源不足不影响正常画面；部分查询仅在析构时释放。
      if (make_query(device, D3D11_QUERY_TIMESTAMP_DISJOINT, &slot->disjoint))
        for (int j = 0; j < 4; j++) if (!make_query(device, D3D11_QUERY_TIMESTAMP, &slot->ticks[j])) break;
    }
  }
  return 1;
}

int tv_readback_submit(tv_color *s, struct tv_readback_slot *slot, const uint8_t *input, int stride, float gain) {
  struct tv_readback *r = s->readback;
  uint64_t start = r->measure ? tv_color_now() : 0;
  int measure_gpu = r->measure && slot->disjoint && slot->ticks[3];
  if (measure_gpu) {
    ID3D11DeviceContext_Begin(r->context, (ID3D11Asynchronous *)slot->disjoint);
    ID3D11DeviceContext_End(r->context, (ID3D11Asynchronous *)slot->ticks[0]);
  }
  if (!pl_tex_upload(s->gpu, pl_tex_transfer_params(.tex = s->input, .ptr = (void *)input,
      .row_pitch = stride, .no_import = true))) return 0;
  if (r->measure) {
    slot->timings.upload_ns = tv_color_now() - start; start = tv_color_now();
    if (measure_gpu) ID3D11DeviceContext_End(r->context, (ID3D11Asynchronous *)slot->ticks[1]);
  }
  if (!tv_color_dispatch(s, slot->output, gain, NULL)) return 0;
  if (r->measure) {
    slot->timings.dispatch_ns = tv_color_now() - start;
    start = tv_color_now();
    if (measure_gpu) ID3D11DeviceContext_End(r->context, (ID3D11Asynchronous *)slot->ticks[2]);
  }
  ID3D11DeviceContext_CopyResource(r->context, (ID3D11Resource *)slot->staging, (ID3D11Resource *)slot->texture);
  if (measure_gpu) {
    ID3D11DeviceContext_End(r->context, (ID3D11Asynchronous *)slot->ticks[3]);
    ID3D11DeviceContext_End(r->context, (ID3D11Asynchronous *)slot->disjoint);
  }
  ID3D11DeviceContext_End(r->context, (ID3D11Asynchronous *)slot->event);
  if (r->measure) slot->timings.download_ns = tv_color_now() - start;
  return 1;
}

int tv_readback_ready(tv_color *s, struct tv_readback_slot *slot) {
  BOOL ready = FALSE;
  HRESULT hr = ID3D11DeviceContext_GetData(s->readback->context, (ID3D11Asynchronous *)slot->event,
      &ready, sizeof(ready), D3D11_ASYNC_GETDATA_DONOTFLUSH);
  if (FAILED(hr)) return TV_COLOR_FAILED;
  return hr == S_OK && ready ? TV_COLOR_OK : TV_COLOR_BUSY;
}

static void read_timings(tv_color *s, struct tv_readback_slot *slot) {
  if (!s->readback->measure || !slot->disjoint || !slot->ticks[3]) return;
  ID3D11DeviceContext *context = s->readback->context;
  D3D11_QUERY_DATA_TIMESTAMP_DISJOINT frequency;
  if (ID3D11DeviceContext_GetData(context, (ID3D11Asynchronous *)slot->disjoint,
      &frequency, sizeof(frequency), D3D11_ASYNC_GETDATA_DONOTFLUSH) != S_OK || frequency.Disjoint || !frequency.Frequency) return;
  uint64_t ticks[4];
  for (int i = 0; i < 4; i++) {
    if (ID3D11DeviceContext_GetData(context, (ID3D11Asynchronous *)slot->ticks[i], &ticks[i], sizeof(ticks[i]),
        D3D11_ASYNC_GETDATA_DONOTFLUSH) != S_OK || (i && ticks[i] < ticks[i - 1])) return;
  }
  slot->timings.upload_gpu_ns = (uint64_t)((ticks[1] - ticks[0]) * 1e9 / frequency.Frequency);
  slot->timings.gpu_ns = (uint64_t)((ticks[2] - ticks[1]) * 1e9 / frequency.Frequency);
  slot->timings.download_gpu_ns = (uint64_t)((ticks[3] - ticks[2]) * 1e9 / frequency.Frequency);
  slot->timings.gpu_valid = 1;
}

int tv_readback_copy(tv_color *s, struct tv_readback_slot *slot, uint8_t *out, int stride) {
  struct tv_readback *r = s->readback;
  if (out) {
    uint64_t start = r->measure ? tv_color_now() : 0;
    D3D11_MAPPED_SUBRESOURCE mapped;
    HRESULT hr = ID3D11DeviceContext_Map(r->context, (ID3D11Resource *)slot->staging, 0,
        D3D11_MAP_READ, D3D11_MAP_FLAG_DO_NOT_WAIT, &mapped);
    if (hr == DXGI_ERROR_WAS_STILL_DRAWING) return TV_COLOR_BUSY;
    if (FAILED(hr)) return TV_COLOR_FAILED;
    if (r->measure) { slot->timings.map_ns = tv_color_now() - start; start = tv_color_now(); }
    int valid = mapped.RowPitch >= (size_t)r->width * 4 && mapped.RowPitch <= r->pitch;
    if (valid) for (int y = 0; y < r->height; y++)
      memcpy(out + (size_t)y * stride, (uint8_t *)mapped.pData + (size_t)y * mapped.RowPitch, (size_t)r->width * 4);
    if (r->measure) slot->timings.copy_ns = tv_color_now() - start;
    ID3D11DeviceContext_Unmap(r->context, (ID3D11Resource *)slot->staging, 0);
    if (!valid) return TV_COLOR_FAILED;
  }
  read_timings(s, slot);
  return TV_COLOR_OK;
}

void tv_readback_release(tv_color *s) {
  struct tv_readback *r = s->readback;
  for (int i = 0; i < TV_COLOR_SLOTS; i++) {
    struct tv_readback_slot *slot = &r->slots[i];
    pl_tex_destroy(s->gpu, &slot->output);
    if (slot->texture) ID3D11Texture2D_Release(slot->texture);
    if (slot->staging) ID3D11Texture2D_Release(slot->staging);
    if (slot->event) ID3D11Query_Release(slot->event);
    if (slot->disjoint) ID3D11Query_Release(slot->disjoint);
    for (int j = 0; j < 4; j++) if (slot->ticks[j]) ID3D11Query_Release(slot->ticks[j]);
  }
  if (r->context) ID3D11DeviceContext_Release(r->context);
}
