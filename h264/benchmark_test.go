package h264

import (
	"termous/video/frame"
	"testing"
)

// 同一合成输入用于与抽离前 RDP 编码路径比较，不代表所有桌面的性能。
func BenchmarkDesktopEncoding(b *testing.B) {
	if !QueryCapabilities().Supported {
		b.Skip("native SDK unavailable")
	}
	for _, s := range []struct {
		name          string
		width, height int
	}{{"1080p", 1920, 1080}, {"4K_to_1080p", 3840, 2160}} {
		b.Run(s.name, func(b *testing.B) {
			e, err := New(Config{Size: frame.Size{Width: 1920, Height: 1080}, Rate: RateControl{Bitrate: 2000000, FPS: 30}, Level: Level40})
			if err != nil {
				b.Fatal(err)
			}
			defer e.Close()
			pixels := make([]byte, s.width*s.height*4)
			for i := 0; i < len(pixels); i += 4 {
				pixels[i] = byte(i / 128)
				pixels[i+1] = byte(i / s.width)
				pixels[i+2] = byte(i / 65536)
				pixels[i+3] = 255
			}
			f := frame.BGRA{Size: frame.Size{Width: s.width, Height: s.height}, Pixels: pixels, Stride: s.width * 4}
			b.ReportAllocs()
			b.ResetTimer()
			for i := 0; i < b.N; i++ {
				pixels[(i*4)%len(pixels)]++
				if _, err := e.EncodeBGRA(f, Options{Keyframe: i%30 == 0, TimestampMS: int64(i * 33)}); err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}
