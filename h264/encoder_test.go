package h264

import (
	"bytes"
	"errors"
	"sync"
	"termous/video/frame"
	"testing"
)

func testConfig() Config {
	return Config{Size: frame.Size{Width: 320, Height: 180}, Rate: RateControl{Bitrate: 500000, FPS: 15}, Level: Level31}
}
func testSource() frame.BGRA {
	f := frame.BGRA{Size: frame.Size{Width: 640, Height: 360}, Stride: 640*4 + 16, Pixels: make([]byte, (640*4+16)*360)}
	for y := 0; y < f.Height; y++ {
		for x := 0; x < f.Width; x++ {
			i := y*f.Stride + x*4
			f.Pixels[i] = byte(x)
			f.Pixels[i+1] = byte(y)
			f.Pixels[i+2] = 255
			f.Pixels[i+3] = 255
		}
	}
	return f
}
func TestEncodingAndOwnership(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	e, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	src := testSource()
	first, err := e.EncodeBGRA(src, Options{Keyframe: true})
	if err != nil || !first.Keyframe || first.Skipped || len(first.Data) == 0 {
		t.Fatalf("keyframe: %+v %v", first, err)
	}
	nals := map[byte]bool{}
	for i := 0; i+4 < len(first.Data); i++ {
		if bytes.Equal(first.Data[i:i+4], []byte{0, 0, 0, 1}) {
			nals[first.Data[i+4]&31] = true
		}
	}
	if !nals[7] || !nals[8] || !nals[5] {
		t.Fatal("missing SPS/PPS/IDR", nals)
	}
	copyOfFirst := bytes.Clone(first.Data)
	for i, rate := range []int{250000, 2160000, 8000000, 100000} {
		if err := e.UpdateRate(RateControl{Bitrate: rate, FPS: 10}); err != nil {
			t.Fatal(err)
		}
		if _, err := e.EncodeBGRA(src, Options{Keyframe: true, TimestampMS: int64((i + 1) * 100)}); err != nil {
			t.Fatal(err)
		}
	}
	e.Close()
	e.Close()
	if !bytes.Equal(first.Data, copyOfFirst) {
		t.Fatal("returned frame was overwritten")
	}
	if _, err := e.EncodeBGRA(src, Options{}); !errors.Is(err, ErrClosed) {
		t.Fatal(err)
	}
}
func TestConcurrentClose(t *testing.T) {
	if !QueryCapabilities().Supported {
		t.Skip("native SDK unavailable")
	}
	e, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	src := testSource()
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_, err := e.EncodeBGRA(src, Options{})
			if err != nil && !errors.Is(err, ErrClosed) {
				t.Error(err)
			}
		}()
	}
	e.Close()
	wg.Wait()
}
func TestConfigurationAndUnavailable(t *testing.T) {
	c := testConfig()
	c.Size = frame.Size{Width: 1920, Height: 1080}
	if _, err := New(c); !errors.Is(err, ErrInvalidConfig) {
		t.Fatal("invalid level accepted", err)
	}
	if !QueryCapabilities().Supported {
		if _, err := New(testConfig()); !errors.Is(err, ErrUnsupported) {
			t.Fatal(err)
		}
	}
}

func TestOutputSizeValidation(t *testing.T) {
	for _, size := range []frame.Size{{Width: 2, Height: 180}, {Width: 320, Height: 14}, {Width: 17, Height: 16}} {
		c := testConfig()
		c.Size = size
		e, err := New(c)
		if e != nil {
			e.Close()
		}
		if !errors.Is(err, ErrInvalidConfig) {
			t.Fatalf("size %+v: %v", size, err)
		}
	}
}
