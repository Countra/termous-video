//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package colornative

/*
#include "bridge.h"
*/
import "C"
import (
	"runtime"
	"termous/video/frame"
	"time"
	"unsafe"
)

func statusError(status C.int) error {
	switch status {
	case 0:
		return nil
	case 2:
		return frame.ErrInvalid
	case 3:
		return ErrBusy
	case 4:
		return ErrUnavailable
	default:
		return ErrFailed
	}
}

func readTimings(t *C.tv_color_timings) Timings {
	return Timings{Submit: time.Duration(t.submit_ns), Validate: time.Duration(t.validate_ns), Upload: time.Duration(t.upload_ns),
		Dispatch: time.Duration(t.dispatch_ns), DownloadWait: time.Duration(t.download_ns),
		DispatchGPU: time.Duration(t.gpu_ns), Map: time.Duration(t.map_ns), Copy: time.Duration(t.copy_ns),
		UploadGPU: time.Duration(t.upload_gpu_ns), DownloadGPU: time.Duration(t.download_gpu_ns), GPUValid: t.gpu_valid != 0}
}

func (p *Processor) Plan(size frame.Size) (Resources, error) {
	var host, device C.uint64_t
	err := statusError(C.tv_color_async_plan(p.ptr, C.int(size.Width), C.int(size.Height), &host, &device))
	return Resources{uint64(host), uint64(device)}, err
}
func (p *Processor) Prepare(size frame.Size, measure bool) error {
	var flag C.int
	if measure {
		flag = 1
	}
	return statusError(C.tv_color_async_prepare(p.ptr, C.int(size.Width), C.int(size.Height), flag))
}
func (p *Processor) Submit(src frame.RGBA16F, sequence uint64) error {
	err := statusError(C.tv_color_async_submit(p.ptr, (*C.uint8_t)(unsafe.Pointer(unsafe.SliceData(src.Pixels))),
		C.size_t(len(src.Pixels)), C.int(src.Stride), C.float(src.SDRWhiteNits), C.uint64_t(sequence)))
	runtime.KeepAlive(src)
	return err
}
func (p *Processor) Ready(sequence uint64) error {
	return statusError(C.tv_color_async_ready(p.ptr, C.uint64_t(sequence)))
}
func (p *Processor) Discard(sequence uint64) error {
	return statusError(C.tv_color_async_discard(p.ptr, C.uint64_t(sequence)))
}
func (p *Processor) Collect(sequence uint64, dst frame.BGRA) (Timings, error) {
	if p.timing == nil {
		p.timing = new(C.tv_color_timings)
	}
	*p.timing = C.tv_color_timings{}
	err := statusError(C.tv_color_async_collect(p.ptr, C.uint64_t(sequence),
		(*C.uint8_t)(unsafe.Pointer(unsafe.SliceData(dst.Pixels))), C.size_t(len(dst.Pixels)), C.int(dst.Stride), p.timing))
	runtime.KeepAlive(dst)
	return readTimings(p.timing), err
}
