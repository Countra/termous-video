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
	var expected [][3]int
	for i := 0; i < 12; i++ {
		var rate *RateControl
		if i == 4 || i == 8 {
			rate = &RateControl{Bitrate: 400_000, FPS: 15}
			if i == 8 {
				rate = &RateControl{Bitrate: 1_000_000, FPS: 15}
			}
		}
		for j := range f.Y {
			f.Y[j] = byte(70 + i*5)
		}
		for j := range f.U {
			f.U[j], f.V[j] = byte(90+i*2), byte(230-i*3)
		}
		expected = append(expected, [3]int{70 + i*5, 90 + i*2, 230 - i*3})
		out, err := e.EncodeI420(f, Options{Rate: rate, Keyframe: i == 0, TimestampMS: int64(i * 67)})
		if err != nil || out.Skipped {
			t.Fatal(out, err)
		}
		if i > 0 && out.Keyframe {
			t.Fatal("rate update forced IDR", i)
		}
		frames = append(frames, out.Data)
	}
	samples, err := native.TestDecodeSamples(frames, c.Size.Width, c.Size.Height)
	if err != nil {
		t.Fatal(err)
	}
	for i, sample := range samples {
		for channel, value := range sample.YUV {
			delta := value - expected[i][channel]
			if delta < -4 || delta > 4 {
				t.Fatalf("decoded frame %d: %v, want %v", i, sample.YUV, expected[i])
			}
		}
	}
}

func TestCandidateConfigurationsRemainDecodableInOneSequence(t *testing.T) {
	size := frame.Size{Width: 320, Height: 180}
	f, err := frame.NewI420(size)
	if err != nil {
		t.Fatal(err)
	}
	for i := range f.Y {
		f.Y[i] = 82
	}
	for i := range f.U {
		f.U[i], f.V[i] = 90, 240
	}
	var frames [][]byte
	for _, mode := range []struct {
		fps   int
		level Level
	}{{30, Level40}, {60, Level51}, {15, Level31}} {
		e, err := New(Config{Size: size, Rate: RateControl{Bitrate: 2_000_000, FPS: mode.fps}, Level: mode.level, Threads: 4})
		if err != nil {
			t.Fatal(err)
		}
		t.Cleanup(e.Close)
		for i := 0; i < 8; i++ {
			out, err := e.EncodeI420(f, Options{Keyframe: i == 0, TimestampMS: int64(len(frames) * 67)})
			if err != nil || out.Skipped || out.Keyframe != (i == 0) {
				t.Fatalf("候选配置 %+v，第 %d 帧：key=%v skipped=%v err=%v", mode, i, out.Keyframe, out.Skipped, err)
			}
			frames = append(frames, out.Data)
		}
		e.Close()
	}
	// 编码器切换后仍使用同一个解码器，验证新 SPS/PPS/IDR 与后续预测帧的衔接。
	samples, err := native.TestDecodeSamples(frames, size.Width, size.Height)
	if err != nil {
		t.Fatal(err)
	}
	for i, sample := range samples {
		for channel, want := range [3]int{82, 90, 240} {
			if delta := sample.YUV[channel] - want; delta < -4 || delta > 4 {
				t.Fatalf("切换后第 %d 帧颜色异常：%v", i, sample.YUV)
			}
		}
	}
}
