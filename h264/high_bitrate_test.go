package h264

import (
	"termous/video/frame"
	"testing"
)

func TestLevelBitrateBoundaries(t *testing.T) {
	for _, tc := range []struct {
		level Level
		rate  int
	}{{Level31, 14_000_000}, {Level32, 20_000_000}, {Level40, 20_000_000}, {Level41, 50_000_000}, {Level42, 50_000_000}, {Level50, 100_000_000}, {Level51, 100_000_000}} {
		c := Config{Size: frame.Size{Width: 320, Height: 180}, Level: tc.level, Rate: RateControl{Bitrate: tc.rate, FPS: 30}}
		if c.Validate() != nil {
			t.Fatalf("等级边界被拒绝：%+v", tc)
		}
		c.Rate.Bitrate++
		if c.Validate() == nil {
			t.Fatalf("等级越界被接受：%+v", tc)
		}
	}
}
