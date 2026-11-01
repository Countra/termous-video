//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package native

/*
#cgo CXXFLAGS: -DTERMOUS_VIDEO_FIXTURE=1
#cgo LDFLAGS: -ltermous_video_openh264
#include <stdint.h>
int tv_test_rate(void);
int tv_test_decode(const uint8_t*, int, int*, int*, int*);
int tv_test_decode_sequence(const uint8_t*, int, const int*, int, int, int, int*);
*/
import "C"

import "unsafe"

func TestRateBoundary() int { return int(C.tv_test_rate()) }

type DecodedSample struct {
	Width, Height int
	YUV           [3]int
}

func TestDecodeSamples(frames [][]byte, width, height int) ([]DecodedSample, error) {
	if len(frames) == 0 || len(frames) > 256 {
		return nil, ErrNative
	}
	var data []byte
	lengths := make([]C.int, len(frames))
	for i, frame := range frames {
		if len(frame) == 0 || len(data)+len(frame) > 64<<20 {
			return nil, ErrNative
		}
		lengths[i] = C.int(len(frame))
		data = append(data, frame...)
	}
	samples := make([]C.int, len(frames)*3)
	if err := status(C.tv_test_decode_sequence((*C.uint8_t)(unsafe.Pointer(&data[0])), C.int(len(data)), &lengths[0], C.int(len(lengths)), C.int(width), C.int(height), &samples[0])); err != nil {
		return nil, err
	}
	result := make([]DecodedSample, len(frames))
	for i := range result {
		result[i] = DecodedSample{Width: width, Height: height, YUV: [3]int{int(samples[i*3]), int(samples[i*3+1]), int(samples[i*3+2])}}
	}
	return result, nil
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
