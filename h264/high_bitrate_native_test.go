//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package h264

import (
	"termous/video/frame"
	"termous/video/internal/native"
	"termous/video/internal/testpattern"
	"testing"
)

func TestNativeABIEnforcesLevelBitrate(t *testing.T) {
	for _, tc := range []struct{ level, bitrate int }{{31, 14_000_000}, {32, 20_000_000}, {40, 20_000_000}, {41, 50_000_000}, {42, 50_000_000}, {50, 100_000_000}, {51, 100_000_000}} {
		// 直接进入 C ABI，避免 Go 参数校验掩盖原生边界错误。
		config := native.Config{Width: 320, Height: 180, Bitrate: tc.bitrate, FPS: 30, Level: tc.level, Matrix: 709}
		e, err := native.New(config)
		if err != nil {
			t.Fatalf("原生创建拒绝合法边界：%+v %v", config, err)
		}
		f, _ := frame.NewI420(frame.Size{Width: 320, Height: 180})
		_, err = e.EncodeI420(f, native.Options{Rate: &native.RateControl{Bitrate: tc.bitrate + 1, FPS: 30}})
		e.Close()
		if err != native.ErrInvalidConfig {
			t.Fatalf("原生速率更新接受越界值：%+v %v", config, err)
		}
		config.Bitrate++
		invalid, err := native.New(config)
		if invalid != nil {
			invalid.Close()
		}
		if err != native.ErrInvalidConfig {
			t.Fatalf("原生创建接受越界值：%+v %v", config, err)
		}
	}
}

func TestHighBitrateRateChangesRemainDecodable(t *testing.T) {
	for _, size := range []frame.Size{{Width: 1920, Height: 1080}, {Width: 2560, Height: 1440}} {
		e, err := New(Config{Size: size, Level: Level51, Rate: RateControl{Bitrate: 24_000_000, FPS: 60}, Matrix: Matrix709})
		if err != nil {
			t.Fatal(err)
		}
		defer e.Close()
		f := frame.BGRA{Size: size, Stride: size.Width * 4, Pixels: make([]byte, size.Width*size.Height*4)}
		var frames [][]byte
		var expected [][3]int
		rates := [...]int{24_000_000, 50_000_000, 100_000_000, 24_000_000}
		for i := 0; i < len(rates)*16; i++ {
			testpattern.Desktop(f, i)
			// 左下角保留对齐宏块的平坦参考区，其余整幅动态素材继续提供编码压力。
			gray := byte(48 + i*2)
			for y := ((size.Height-1)/16 - 1) * 16; y < size.Height; y++ {
				for x := 0; x < 32; x++ {
					pixel := f.Pixels[y*f.Stride+x*4:][:4]
					pixel[0], pixel[1], pixel[2], pixel[3] = gray, gray, gray, 255
				}
			}
			var rate *RateControl
			if i%16 == 0 {
				rate = &RateControl{Bitrate: rates[i/16], FPS: 60}
			}
			out, err := e.EncodeBGRA(f, Options{Rate: rate, Keyframe: i == 0, TimestampMS: int64(i * 17)})
			if err != nil || out.Skipped || i > 0 && out.Keyframe {
				t.Fatalf("%+v/frame %d: skipped=%v key=%v err=%v", size, i, out.Skipped, out.Keyframe, err)
			}
			frames = append(frames, out.Data)
			// 独立有限范围公式不依赖生产 libyuv 转换，也不从解码输出生成期望值。
			expected = append(expected, [3]int{16 + (219*int(gray)+127)/255, 128, 128})
		}
		samples, err := native.TestDecodeSamples(frames, size.Width, size.Height)
		if err != nil {
			t.Fatal(err)
		}
		for i, sample := range samples {
			for channel, value := range sample.YUV {
				if delta := value - expected[i][channel]; delta < -4 || delta > 4 {
					t.Fatalf("%+v/frame %d: %v, want %v", size, i, sample.YUV, expected[i])
				}
			}
		}
	}
}
