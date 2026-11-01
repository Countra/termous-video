package testpattern

import (
	"termous/video/frame"
	"testing"
)

func TestDesktopMatchesIndependentScalarPattern(t *testing.T) {
	for _, size := range []frame.Size{{Width: 16, Height: 16}, {Width: 129, Height: 97}, {Width: 2110, Height: 33}} {
		f := frame.BGRA{Size: size, Stride: size.Width*4 + 8, Pixels: make([]byte, (size.Width*4+8)*size.Height)}
		for _, n := range []int{0, 1, 191, 3839, 99999} {
			Desktop(f, n)
			for y := 0; y < size.Height; y++ {
				for x := 0; x < size.Width; x++ {
					sx, sy := x+n*7, y+n*3
					v := byte(224)
					if sy%28 < 14 && sx%96 < 76 && (sx/4+sy/3)%5 != 0 {
						v = 40
					}
					want := [4]byte{v, v, v, 255}
					if x > size.Width/2 {
						want = [4]byte{byte(sx/3 + sy/5), byte(sx/7 + sy/2), byte(sx/5 + sy/9), 255}
					}
					wx := (n * 13) % max(1, size.Width*3/4)
					if x >= wx && x < wx+size.Width/4 && y > size.Height/3 && y < size.Height*2/3 {
						want = [4]byte{byte((x - wx) * 3), byte(y * 2), byte((x - wx) ^ y), 255}
					}
					i := y*f.Stride + x*4
					if got := [4]byte(f.Pixels[i : i+4]); got != want {
						t.Fatalf("%+v frame %d pixel %d,%d: %v != %v", size, n, x, y, got, want)
					}
				}
			}
		}
	}
}
