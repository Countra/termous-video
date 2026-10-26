//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package native

/*
#include <stdint.h>
int tv_test_rate(void);
int tv_test_decode(const uint8_t*, int, int*, int*, int*);
*/
import "C"

import "unsafe"

func TestRateBoundary() int { return int(C.tv_test_rate()) }

type DecodedSample struct {
	Width, Height int
	YUV           [3]int
}

func TestDecode(data []byte) (DecodedSample, error) {
	if len(data) == 0 {
		return DecodedSample{}, ErrNative
	}
	var w, h C.int
	var yuv [3]C.int
	code := C.tv_test_decode((*C.uint8_t)(unsafe.Pointer(&data[0])), C.int(len(data)), &w, &h, &yuv[0])
	return DecodedSample{Width: int(w), Height: int(h), YUV: [3]int{int(yuv[0]), int(yuv[1]), int(yuv[2])}}, status(code)
}
