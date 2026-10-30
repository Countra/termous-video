//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package h264

import (
	"termous/video/frame"
	"termous/video/internal/native"
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
		err = e.UpdateRate(tc.bitrate+1, 30)
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
		f, err := frame.NewI420(size)
		if err != nil {
			t.Fatal(err)
		}
		for i := range f.Y {
			f.Y[i] = byte(16 + i%220)
		}
		for i := range f.U {
			f.U[i], f.V[i] = 100, 160
		}
		var frames [][]byte
		for i, rate := range []int{24_000_000, 50_000_000, 100_000_000, 24_000_000} {
			if err := e.UpdateRate(RateControl{Bitrate: rate, FPS: 60}); err != nil {
				t.Fatal(err)
			}
			f.Y[i]++
			out, err := e.EncodeI420(f, Options{Keyframe: i == 0, TimestampMS: int64(i * 17)})
			if err != nil || out.Skipped || i > 0 && out.Keyframe {
				t.Fatalf("%+v/%d: skipped=%v key=%v err=%v", size, rate, out.Skipped, out.Keyframe, err)
			}
			frames = append(frames, out.Data)
		}
		if err := native.TestDecodeSequence(frames, size.Width, size.Height); err != nil {
			t.Fatal(err)
		}
	}
}
