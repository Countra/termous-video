//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package colornative

/*
#include "bridge.h"
*/
import "C"
import (
	"runtime"
	"termous/video/frame"
	"unsafe"
)

const Supported = true

type Processor struct {
	ptr    *C.tv_color
	device string
	timing *C.tv_color_timings
}

func New(software bool) (*Processor, error) {
	var mode C.int
	if software {
		mode = 1
	}
	p := C.tv_color_create(mode)
	if p == nil {
		return nil, ErrUnavailable
	}
	return &Processor{ptr: p, device: C.GoString(C.tv_color_device(p))}, nil
}
func (p *Processor) Close()          { C.tv_color_destroy(p.ptr); p.ptr = nil }
func (p *Processor) Backend() string { return C.GoString(C.tv_color_backend(p.ptr)) }
func (p *Processor) Device() string  { return p.device }
func (p *Processor) Failed() bool    { return C.tv_color_failed(p.ptr) != 0 }
func (p *Processor) Process(src frame.RGBA16F, dst frame.BGRA, timings *Timings) error {
	var measure *C.tv_color_timings
	if timings != nil {
		// cgo 参数会逃逸到堆；诊断缓冲随处理器复用，关闭诊断时不分配。
		if p.timing == nil {
			p.timing = new(C.tv_color_timings)
		}
		measure = p.timing
		*timings = Timings{}
	}
	status := C.tv_color_process(p.ptr, (*C.uint8_t)(unsafe.Pointer(unsafe.SliceData(src.Pixels))), C.size_t(len(src.Pixels)),
		C.int(src.Width), C.int(src.Height), C.int(src.Stride), C.float(src.SDRWhiteNits),
		(*C.uint8_t)(unsafe.Pointer(unsafe.SliceData(dst.Pixels))), C.size_t(len(dst.Pixels)), C.int(dst.Stride), measure)
	runtime.KeepAlive(src)
	runtime.KeepAlive(dst)
	if err := statusError(status); err != nil {
		return err
	}
	if timings != nil {
		*timings = readTimings(measure)
	}
	return nil
}
