package h264

import "testing"

func TestLowFPSAndSubKilobitRateUpdates(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	for _, fps := range []int{1, 2, 3, 4, 60} {
		config := testConfig()
		config.Rate = RateControl{Bitrate: 100_999, FPS: fps}
		e, err := New(config)
		if err != nil {
			t.Fatalf("fps=%d: %v", fps, err)
		}
		t.Cleanup(e.Close)
		// 覆盖不足四帧时的 VBV 下限，以及跨越和未跨越 kbit/s 边界的更新。
		for _, bitrate := range []int{100_999, 101_001, 100_001, 100_999} {
			rate := RateControl{Bitrate: bitrate, FPS: fps}
			out, err := e.EncodeBGRA(testSource(), Options{Rate: &rate})
			if err != nil || out.Skipped || len(out.Data) == 0 || e.config.Rate != rate {
				t.Fatalf("rate=%+v: skipped=%v err=%v", rate, out.Skipped, err)
			}
		}
		e.Close()
	}
}
