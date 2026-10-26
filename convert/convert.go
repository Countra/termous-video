// Package convert 提供同步颜色转换与缩放，输出缓冲由调用方持有。
package convert

import (
	"termous/video/frame"
	"termous/video/internal/buffer"
	"termous/video/internal/native"
)

var (
	ErrUnsupported = native.ErrUnsupported
	ErrNative      = native.ErrNative
)

func Supported() bool { return native.Supported }

func BGRAToI420(src frame.BGRA, dst frame.I420) error {
	if src.Validate() != nil || dst.Validate() != nil || src.Size != dst.Size || !buffer.Distinct(src.Pixels, dst.Y, dst.U, dst.V) {
		return frame.ErrInvalid
	}
	return native.Convert(src, dst)
}

func ScaleI420(src, dst frame.I420) error {
	if src.Validate() != nil || dst.Validate() != nil || !buffer.Distinct(dst.Y, dst.U, dst.V) {
		return frame.ErrInvalid
	}
	for _, a := range [][]byte{src.Y, src.U, src.V} {
		for _, b := range [][]byte{dst.Y, dst.U, dst.V} {
			if buffer.Overlap(a, b) {
				return frame.ErrInvalid
			}
		}
	}
	return native.Scale(src, dst)
}
