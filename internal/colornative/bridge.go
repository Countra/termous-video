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

type Processor struct{ ptr *C.tv_color }

func New(software bool) (*Processor, error) {
	var mode C.int
	if software {
		mode = 1
	}
	p := C.tv_color_create(mode)
	if p == nil {
		return nil, ErrUnavailable
	}
	return &Processor{p}, nil
}
func (p *Processor) Close()          { C.tv_color_destroy(p.ptr); p.ptr = nil }
func (p *Processor) Backend() string { return C.GoString(C.tv_color_backend(p.ptr)) }
func (p *Processor) Failed() bool    { return C.tv_color_failed(p.ptr) != 0 }
func (p *Processor) Process(src frame.RGBA16F, dst frame.BGRA) error {
	status := C.tv_color_process(p.ptr, (*C.uint8_t)(unsafe.Pointer(unsafe.SliceData(src.Pixels))), C.size_t(len(src.Pixels)),
		C.int(src.Width), C.int(src.Height), C.int(src.Stride), C.float(src.PeakNits),
		(*C.uint8_t)(unsafe.Pointer(unsafe.SliceData(dst.Pixels))), C.size_t(len(dst.Pixels)), C.int(dst.Stride))
	runtime.KeepAlive(src)
	runtime.KeepAlive(dst)
	if status == 2 {
		return frame.ErrInvalid
	}
	if status != 0 {
		return ErrFailed
	}
	return nil
}
