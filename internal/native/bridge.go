//go:build cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package native

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

type Encoder struct{ pointer *C.tv_encoder }

func status(code C.int) error {
	switch code {
	case C.TV_OK:
		return nil
	case C.TV_UNUSABLE:
		return ErrUnusable
	case C.TV_INVALID:
		return ErrInvalidConfig
	default:
		return ErrNative
	}
}
func New(c Config) (*Encoder, error) {
	var pointer *C.tv_encoder
	err := status(C.tv_create(C.tv_config{width: C.int(c.Width), height: C.int(c.Height), bitrate: C.int(c.Bitrate), fps: C.int(c.FPS), level: C.int(c.Level), matrix: C.int(c.Matrix)}, &pointer))
	if err != nil {
		return nil, err
	}
	if pointer == nil {
		return nil, ErrNative
	}
	return &Encoder{pointer: pointer}, nil
}
func (e *Encoder) Close() { C.tv_destroy(e.pointer); e.pointer = nil }
func (e *Encoder) UpdateRate(rate, fps int) error {
	return status(C.tv_rate(e.pointer, C.int(rate), C.int(fps)))
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
	return Output{Data: C.GoBytes(unsafe.Pointer(out.data), out.length), Keyframe: out.keyframe != 0, Skipped: out.skipped != 0}, nil
}
func (e *Encoder) EncodeBGRA(f frame.BGRA, key bool, timestamp int64) (Output, error) {
	var out C.tv_output
	code := C.tv_encode_bgra(e.pointer, bytes(f.Pixels), C.size_t(len(f.Pixels)), C.int(f.Width), C.int(f.Height), C.int(f.Stride), force(key), C.int64_t(timestamp), &out)
	runtime.KeepAlive(f)
	return output(out, code)
}
func (e *Encoder) EncodeI420(f frame.I420, key bool, timestamp int64) (Output, error) {
	var out C.tv_output
	code := C.tv_encode_i420(e.pointer, i420(f), force(key), C.int64_t(timestamp), &out)
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
