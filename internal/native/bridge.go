//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package native

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

const Supported = true

type Encoder struct{ pointer *C.tv_encoder }

func status(code C.int) error {
	switch code {
	case C.TV_OK:
		return nil
	case C.TV_UNUSABLE:
		return ErrUnusable
	case C.TV_RECONFIGURE:
		return ErrReconfigureRequired
	case C.TV_INVALID:
		return ErrInvalidConfig
	default:
		return ErrNative
	}
}
func New(c Config) (*Encoder, error) {
	if c.Threads == 0 {
		c.Threads = min(runtime.GOMAXPROCS(0), 16)
	}
	var pointer *C.tv_encoder
	err := status(C.tv_create(C.tv_config{width: C.int(c.Width), height: C.int(c.Height), bitrate: C.int(c.Bitrate), fps: C.int(c.FPS), level: C.int(c.Level), matrix: C.int(c.Matrix), threads: C.int(c.Threads)}, &pointer))
	if err != nil {
		return nil, err
	}
	if pointer == nil {
		return nil, ErrNative
	}
	return &Encoder{pointer: pointer}, nil
}
func (e *Encoder) Close() { C.tv_destroy(e.pointer); e.pointer = nil }
func (e *Encoder) Info() (Info, error) {
	var out C.tv_info
	if err := status(C.tv_get_info(e.pointer, &out)); err != nil {
		return Info{}, err
	}
	return Info{Implementation: C.GoString(out.implementation), Version: C.GoString(out.version), Preset: C.GoString(out.preset), Threads: int(out.threads)}, nil
}
func bytes(p []byte) *C.uint8_t { return (*C.uint8_t)(unsafe.Pointer(unsafe.SliceData(p))) }
func plane(p []byte, stride int) C.tv_plane {
	return C.tv_plane{data: bytes(p), length: C.size_t(len(p)), stride: C.int(stride)}
}
func i420(f frame.I420) C.tv_i420 {
	return C.tv_i420{y: plane(f.Y, f.YStride), u: plane(f.U, f.UStride), v: plane(f.V, f.VStride), width: C.int(f.Width), height: C.int(f.Height)}
}
func force(v bool) C.int {
	if v {
		return 1
	}
	return 0
}
func output(out C.tv_output, code C.int) (Output, error) {
	if err := status(code); err != nil {
		return Output{}, err
	}
	if out.length < 0 || out.length > 4*1024*1024 || (out.length > 0 && out.data == nil) {
		return Output{}, ErrNative
	}
	return Output{QPPlusOne: uint8(out.qp_plus_one), ConversionTime: time.Duration(out.conversion_ns), EncodingTime: time.Duration(out.encoding_ns), Data: C.GoBytes(unsafe.Pointer(out.data), out.length), Keyframe: out.keyframe != 0, Skipped: out.skipped != 0}, nil
}
func options(o Options) C.tv_options {
	r := C.tv_options{measure_stages: force(o.MeasureStages), keyframe: force(o.Keyframe), timestamp: C.int64_t(o.TimestampMS)}
	if o.Rate != nil {
		r.rate_present = 1
		r.bitrate, r.fps = C.int(o.Rate.Bitrate), C.int(o.Rate.FPS)
	}
	return r
}
func (e *Encoder) EncodeBGRA(f frame.BGRA, o Options) (Output, error) {
	var out C.tv_output
	code := C.tv_encode_bgra(e.pointer, bytes(f.Pixels), C.size_t(len(f.Pixels)), C.int(f.Width), C.int(f.Height), C.int(f.Stride), options(o), &out)
	runtime.KeepAlive(f)
	return output(out, code)
}
func (e *Encoder) EncodeI420(f frame.I420, o Options) (Output, error) {
	var out C.tv_output
	code := C.tv_encode_i420(e.pointer, i420(f), options(o), &out)
	runtime.KeepAlive(f)
	return output(out, code)
}
func Convert(src frame.BGRA, dst frame.I420) error {
	code := C.tv_convert(bytes(src.Pixels), C.size_t(len(src.Pixels)), C.int(src.Width), C.int(src.Height), C.int(src.Stride), i420(dst))
	runtime.KeepAlive(src)
	runtime.KeepAlive(dst)
	return status(code)
}
func Scale(src, dst frame.I420) error {
	code := C.tv_scale(i420(src), i420(dst))
	runtime.KeepAlive(src)
	runtime.KeepAlive(dst)
	return status(code)
}
