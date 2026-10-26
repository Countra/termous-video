package h264

import (
	"bytes"
	"errors"
	"testing"

	"termous/video/frame"
)

func TestBaselineLevelAndOddPaddedSource(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	for _, level := range []Level{Level31, Level40} {
		config := testConfig()
		config.Level = level
		e, err := New(config)
		if err != nil {
			t.Fatal(err)
		}
		src := frame.BGRA{Size: frame.Size{Width: 321, Height: 181}, Stride: 321*4 + 12}
		src.Pixels = make([]byte, src.Stride*(src.Height-1)+src.Width*4)
		out, err := e.EncodeBGRA(src, Options{Keyframe: true})
		e.Close()
		if err != nil || !out.Keyframe || out.Skipped {
			t.Fatalf("odd padded source: %v", err)
		}
		// SPS 前四字节依次为 NAL、profile_idc、约束标志、level_idc，无需解析可变长字段。
		found := false
		for i := 0; i+8 <= len(out.Data); i++ {
			if bytes.Equal(out.Data[i:i+4], []byte{0, 0, 0, 1}) && out.Data[i+4]&31 == 7 {
				found = true
				if out.Data[i+5] != 66 || out.Data[i+7] != byte(level) {
					t.Fatalf("unexpected profile/level: %d/%d", out.Data[i+5], out.Data[i+7])
				}
			}
		}
		if !found {
			t.Fatal("missing SPS")
		}
	}
}

func TestRejectedInputLeavesEncoderUsable(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	e, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	f := testSource()
	f.Pixels = f.Pixels[:5]
	if _, err := e.EncodeBGRA(f, Options{}); !errors.Is(err, frame.ErrInvalid) {
		t.Fatal("short source accepted", err)
	}
	wrongSize, err := frame.NewI420(frame.Size{Width: 2, Height: 2})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := e.EncodeI420(wrongSize, Options{}); !errors.Is(err, frame.ErrInvalid) {
		t.Fatal("mismatched I420 accepted", err)
	}
	if err := e.UpdateRate(RateControl{Bitrate: 1, FPS: 30}); !errors.Is(err, ErrInvalidConfig) {
		t.Fatal("invalid budget accepted", err)
	}
	if _, err := e.EncodeBGRA(testSource(), Options{Keyframe: true}); err != nil {
		t.Fatal("validation failure changed native state", err)
	}
}
