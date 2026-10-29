package frame

import (
	"math"
	"testing"
)

func TestHDRWhiteContract(t *testing.T) {
	f := RGBA16F{Size: Size{Width: 1, Height: 1}, Stride: 8, Pixels: make([]byte, 8)}
	for _, v := range []float32{0, -1, 10001, float32(math.NaN()), float32(math.Inf(1)), math.SmallestNonzeroFloat32} {
		f.SDRWhiteNits = v
		if f.Validate() != ErrInvalid {
			t.Fatalf("invalid white accepted: %g", v)
		}
	}
	for _, v := range []float32{80, 120, 200, 300, 400, 10000} {
		f.SDRWhiteNits = v
		if err := f.Validate(); err != nil {
			t.Fatalf("white %g: %v", v, err)
		}
	}
}
