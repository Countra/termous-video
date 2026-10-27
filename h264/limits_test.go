package h264

import (
	"termous/video/frame"
	"testing"
)

func TestLevelCombinations(t *testing.T) {
	for _, tc := range []struct {
		w, h, fps int
		level     Level
	}{{1280, 720, 30, Level31}, {1280, 720, 60, Level32}, {1920, 1080, 30, Level40}, {1920, 1080, 60, Level42}, {2560, 1440, 30, Level50}, {2560, 1440, 60, Level51}, {1440, 2560, 60, Level51}} {
		c := Config{Size: frame.Size{Width: tc.w, Height: tc.h}, Rate: RateControl{Bitrate: 8_000_000, FPS: tc.fps}, Level: tc.level}
		level, err := MinimumLevel(c.Size, c.Rate)
		if err != nil || level != tc.level {
			t.Fatalf("%+v: %v %v", tc, level, err)
		}
		if c.Validate() != nil {
			t.Fatalf("valid mode rejected: %+v", tc)
		}
		if !QueryCapabilities().Supported {
			continue
		}
		e, err := New(c)
		if err != nil {
			t.Fatal(err)
		}
		pixels := make([]byte, tc.w*tc.h*4)
		for i := 0; i < len(pixels); i += 4 {
			pixels[i] = 32
			pixels[i+1] = 128
			pixels[i+2] = 224
			pixels[i+3] = 255
		}
		out, err := e.EncodeBGRA(frame.BGRA{Size: c.Size, Pixels: pixels, Stride: tc.w * 4}, Options{Keyframe: true})
		if err != nil || !out.Keyframe || len(out.Data) == 0 {
			t.Fatalf("encode %+v: %v", tc, err)
		}
		if tc.level == Level40 && e.UpdateRate(RateControl{Bitrate: 8_000_000, FPS: 60}) != ErrInvalidConfig {
			t.Fatal("rate update bypassed level limit")
		}
		e.Close()
	}
}
