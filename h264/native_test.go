//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package h264

import (
	"termous/video/frame"
	"termous/video/internal/native"
	"testing"
)

func TestNativeBudgetFailureRestoresOrInvalidates(t *testing.T) {
	if native.TestRateBoundary() != 0 {
		t.Fatal("native rollback contract failed")
	}
}
func TestI420DecodesWithExpectedDimensionsAndLuma(t *testing.T) {
	e, err := New(testConfig())
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	f, _ := frame.NewI420(testConfig().Size)
	for i := range f.Y {
		f.Y[i] = 82
	}
	for i := range f.U {
		f.U[i] = 90
	}
	for i := range f.V {
		f.V[i] = 240
	}
	out, err := e.EncodeI420(f, Options{Keyframe: true})
	if err != nil {
		t.Fatal(err)
	}
	sample, err := native.TestDecode(out.Data)
	if err != nil || sample.Width != f.Width || sample.Height != f.Height || sample.YUV[0] < 79 || sample.YUV[0] > 85 {
		t.Fatalf("decoded %+v: %v", sample, err)
	}
}

func TestMinimumOutputSizeDecodes(t *testing.T) {
	c := testConfig()
	c.Size = QueryCapabilities().MinSize
	e, err := New(c)
	if err != nil {
		t.Fatal(err)
	}
	defer e.Close()
	f, err := frame.NewI420(c.Size)
	if err != nil {
		t.Fatal(err)
	}
	out, err := e.EncodeI420(f, Options{Keyframe: true})
	if err != nil {
		t.Fatal(err)
	}
	sample, err := native.TestDecode(out.Data)
	if err != nil || sample.Width != c.Size.Width || sample.Height != c.Size.Height {
		t.Fatalf("decoded %+v: %v", sample, err)
	}
}
