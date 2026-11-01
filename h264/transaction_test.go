package h264

import (
	"errors"
	"fmt"
	"termous/video/frame"
	"testing"
)

func TestFrameRateChangeRequiresCandidateWithoutChangingCurrent(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	e, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	src := testSource()
	if _, err = e.EncodeBGRA(src, Options{}); err != nil {
		t.Fatal(err)
	}
	if _, err = e.EncodeBGRA(src, Options{Rate: &RateControl{Bitrate: 700000, FPS: 30}}); !errors.Is(err, ErrReconfigureRequired) {
		t.Fatal("FPS change was silently accepted", err)
	}
	if e.config.Rate != testConfig().Rate {
		t.Fatal("rejected rate changed config", e.config)
	}
	out, err := e.EncodeBGRA(src, Options{})
	if err != nil || out.Keyframe {
		t.Fatal("rejection damaged reference chain", err)
	}
	bad := src
	bad.Pixels = nil
	if _, err = e.EncodeBGRA(bad, Options{Rate: &RateControl{Bitrate: 900000, FPS: 15}}); err == nil {
		t.Fatal("invalid frame accepted")
	}
	if _, err = e.EncodeBGRA(src, Options{}); err != nil || e.config.Rate != testConfig().Rate {
		t.Fatal("failed frame left pending rate", err)
	}
}

func TestThreadBudgetAndInformation(t *testing.T) {
	for _, threads := range []int{-1, 17} {
		c := testConfig()
		c.Threads = threads
		if c.Validate() == nil {
			t.Fatal("invalid thread budget", threads)
		}
	}
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	for _, threads := range []int{0, 1, 4, 8, 16} {
		t.Run(fmt.Sprint(threads), func(t *testing.T) {
			c := Config{Size: frame.Size{Width: 1920, Height: 1080}, Rate: RateControl{Bitrate: 24000000, FPS: 60}, Level: Level51, Threads: threads}
			e, err := New(c)
			if err != nil {
				t.Fatal(err)
			}
			defer e.Close()
			info := e.Info()
			if info.Implementation != "x264" || info.Version == "" || info.Preset != "superfast/zerolatency" || info.Threads < 1 || info.Threads > 16 || threads > 0 && info.Threads != threads {
				t.Fatal(info)
			}
			f, _ := frame.NewI420(c.Size)
			out, err := e.EncodeI420(f, Options{})
			if err != nil || !out.Keyframe || out.Skipped {
				t.Fatal("threaded encode", err)
			}
			slices := 0
			for i := 0; i+3 < len(out.Data); i++ {
				if out.Data[i] == 0 && out.Data[i+1] == 0 && out.Data[i+2] == 1 && out.Data[i+3]&31 == 5 {
					slices++
				}
			}
			if slices != info.Threads {
				t.Fatal("unexpected slice count", slices, info)
			}
		})
	}
}

func TestSmallFrameClampsThreadsAndPreservesInformationAfterClose(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	for _, size := range []frame.Size{{Width: 16, Height: 16}, {Width: 320, Height: 180}} {
		config := testConfig()
		config.Size, config.Threads = size, 16
		e, err := New(config)
		if err != nil {
			t.Fatal(err)
		}
		info := e.Info()
		e.Close()
		if want := max(1, ((size.Height+15)/16)/4); info.Threads != want {
			t.Fatalf("%+v: 实际线程数 %d，预期 %d", size, info.Threads, want)
		}
		if e.Info() != info {
			t.Fatal("关闭改变了已确认的编码器信息")
		}
	}
}
