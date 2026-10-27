//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package h264

import (
	"bytes"
	"termous/video/frame"
	"termous/video/internal/native"
	"testing"
)

func TestExtendedModesDecode(t *testing.T) {
	for _, size := range []frame.Size{{Width: 1280, Height: 720}, {Width: 1920, Height: 1080}, {Width: 2560, Height: 1440}, {Width: 1440, Height: 2560}} {
		for _, fps := range []int{30, 60} {
			rate := RateControl{Bitrate: 8_000_000, FPS: fps}
			level, err := MinimumLevel(size, rate)
			if err != nil {
				t.Fatal(err)
			}
			e, err := New(Config{Size: size, Rate: rate, Level: level, Matrix: Matrix709})
			if err != nil {
				t.Fatal(err)
			}
			src := frame.BGRA{Size: size, Stride: size.Width * 4, Pixels: bytes.Repeat([]byte{32, 128, 224, 255}, size.Width*size.Height)}
			out, err := e.EncodeBGRA(src, Options{Keyframe: true})
			e.Close()
			if err != nil {
				t.Fatal(err)
			}
			decoded, err := native.TestDecode(out.Data)
			if err != nil || decoded.Width != size.Width || decoded.Height != size.Height {
				t.Fatalf("%+v/%d 解码结果=%+v err=%v", size, fps, decoded, err)
			}
			found := false
			for i := 0; i+8 < len(out.Data); i++ {
				if bytes.Equal(out.Data[i:i+5], []byte{0, 0, 0, 1, 0x67}) {
					found = true
					if out.Data[i+5] != 66 || out.Data[i+7] != byte(level) {
						t.Fatalf("SPS Profile/Level 错误：%v", out.Data[i+5:i+8])
					}
				}
			}
			if !found {
				t.Fatal("缺少 SPS")
			}
		}
	}
}
