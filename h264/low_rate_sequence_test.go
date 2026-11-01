//go:build video_native_fixture

package h264

import (
	"termous/video/frame"
	"termous/video/internal/native"
	"testing"
)

// 覆盖故障日志中的极低预算和多切片，严格解码不得用错误隐藏掩盖参考链损坏。
func TestLowRateMultiSliceReferenceChain(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	size := frame.Size{Width: 2560, Height: 1440}
	e, err := New(Config{Size: size, Rate: RateControl{Bitrate: 3_200_000, FPS: 60}, Level: Level51, Matrix: Matrix709, Threads: 16})
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	source := frame.BGRA{Size: size, Stride: size.Width * 4, Pixels: make([]byte, size.Width*size.Height*4)}
	frames := make([][]byte, 0, 180)
	for index := 0; index < 180; index++ {
		for y := 0; y < size.Height; y++ {
			for x := 0; x < size.Width; x++ {
				i := y*source.Stride + x*4
				v := ((x+index*13)/13 + (y+index*7)/9)
				source.Pixels[i], source.Pixels[i+1], source.Pixels[i+2], source.Pixels[i+3] = byte(v*41), byte(v*73), byte(v*109), 255
			}
		}
		var rate *RateControl
		if index == 60 {
			rate = &RateControl{Bitrate: 256_000, FPS: 60}
		}
		if index == 120 {
			rate = &RateControl{Bitrate: 4_000_000, FPS: 60}
		}
		out, err := e.EncodeBGRA(source, Options{Rate: rate, TimestampMS: int64(index * 1000 / 60), Keyframe: index == 0})
		if err != nil || out.Skipped || out.QPPlusOne < 1 || out.QPPlusOne > 70 {
			t.Fatalf("帧 %d: %v qp=%d", index, err, out.QPPlusOne)
		}
		frames = append(frames, out.Data)
	}
	if _, err := native.TestDecodeSamples(frames, size.Width, size.Height); err != nil {
		t.Fatal("连续解码失败", err)
	}
}
