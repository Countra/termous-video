package color

import (
	"math"
	"testing"
)

func TestDesktopGradientsAndNegativePrimaries(t *testing.T) {
	if !QueryCapabilities().Compiled {
		t.Skip("native color unavailable")
	}
	p := newTestProcessor(t, false)
	var rgb [][3]float64
	for i := 0; i < 256; i++ {
		v := srgbDecode(float64(i) / 255)
		rgb = append(rgb, [3]float64{v, v, v})
	}
	wide := [][3]float64{{1.22494, -.04206, -.01964}, {-.22494, 1.04206, -.07864}, {1.66049, -.12455, -.01815}, {-.58764, 1.13290, -.10058}}
	for _, v := range wide {
		clipped := v
		for c := range clipped {
			clipped[c] = math.Max(0, math.Min(1, clipped[c]))
		}
		rgb = append(rgb, v, clipped)
	}
	src, dst := fixtureFrame(rgb, 200)
	if err := p.Process(src, dst); err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 256; i++ {
		for c := 0; c < 3; c++ {
			got := dst.Pixels[i*4+c]
			if math.Abs(float64(got)-desktopReference(rgb[i][c])) > 2 {
				t.Fatalf("gradient %d/%d: %d", i, c, got)
			}
			if i > 0 && int(got) < int(dst.Pixels[(i-1)*4+c])-1 {
				t.Fatalf("gradient reversed at %d", i)
			}
		}
	}
	for i := range wide {
		start := (256 + i*2) * 4
		delta := 0
		for c := 0; c < 3; c++ {
			delta += int(math.Abs(float64(dst.Pixels[start+c]) - float64(dst.Pixels[start+4+c])))
		}
		if delta < 3 {
			t.Fatalf("wide-gamut sample %d behaves as preclipped scRGB: %v", i, dst.Pixels[start:start+8])
		}
	}
}
