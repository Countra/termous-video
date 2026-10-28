//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package h264

import (
	"termous/video/frame"
	"termous/video/internal/native"
	"testing"
)

func TestRateUpdatesPreserveDecodableReferenceChain(t *testing.T) {
	c := testConfig()
	e, err := New(c)
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	f, err := frame.NewI420(c.Size)
	if err != nil {
		t.Fatal(err)
	}
	for i := range f.Y {
		f.Y[i] = 82
	}
	for i := range f.U {
		f.U[i] = 90
		f.V[i] = 240
	}
	var frames [][]byte
	for i := 0; i < 12; i++ {
		if i == 4 || i == 8 {
			rate := RateControl{Bitrate: 400_000, FPS: 15}
			if i == 8 {
				rate = RateControl{Bitrate: 1_000_000, FPS: 30}
			}
			if err := e.UpdateRate(rate); err != nil {
				t.Fatal(err)
			}
		}
		f.Y[i]++
		out, err := e.EncodeI420(f, Options{Keyframe: i == 0, TimestampMS: int64(i * 67)})
		if err != nil || out.Skipped {
			t.Fatal(out, err)
		}
		if i > 0 && out.Keyframe {
			t.Fatal("rate update forced IDR", i)
		}
		frames = append(frames, out.Data)
	}
	if err := native.TestDecodeSequence(frames, c.Size.Width, c.Size.Height); err != nil {
		t.Fatal(err)
	}
}
