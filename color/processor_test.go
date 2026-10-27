package color

import (
	"encoding/binary"
	"errors"
	"os"
	"runtime"
	"termous/video/frame"
	"testing"
)

func TestSyntheticHDR(t *testing.T) {
	var reference []byte
	for _, software := range []bool{false, true} {
		if software && runtime.GOOS != "windows" {
			continue
		}
		p, err := New(Options{Software: software})
		if err != nil {
			if !QueryCapabilities().Compiled || os.Getenv("TERMOUS_VIDEO_REQUIRE_COLOR") != "1" && runtime.GOOS != "windows" && errors.Is(err, ErrUnavailable) {
				t.Skipf("GPU unavailable: %v", err)
			}
			t.Fatal(err)
		}
		src := frame.RGBA16F{Size: frame.Size{Width: 64, Height: 16}, Stride: 64*8 + 16, PeakNits: 1000}
		src.Pixels = make([]byte, src.Stride*src.Height)
		values := []uint16{0, 0x3400, 0x3c00, 0x4400, 0x4a40}
		for y := 0; y < src.Height; y++ {
			for x := 0; x < src.Width; x++ {
				for c := 0; c < 4; c++ {
					v := values[x*5/src.Width]
					if y >= 8 {
						v = 0
						if c == x*3/src.Width {
							v = 0x3c00
						}
					}
					if c == 3 {
						v = 0x3c00
					}
					binary.LittleEndian.PutUint16(src.Pixels[y*src.Stride+x*8+c*2:], v)
				}
			}
		}
		dst := frame.BGRA{Size: src.Size, Stride: 64*4 + 16, Pixels: make([]byte, (64*4+16)*16)}
		for repeat := 0; repeat < 3; repeat++ {
			if err = p.Process(src, dst); err != nil {
				t.Fatal(err)
			}
			previous := -1
			for band := 0; band < 5; band++ {
				x := (2*band + 1) * 64 / 10
				pixel := dst.Pixels[4*dst.Stride+x*4:]
				v := int(pixel[0])
				if v <= previous || pixel[3] < 254 {
					t.Fatalf("gray band %d: %v", band, pixel[:4])
				}
				previous = v
			}
			for c := 0; c < 3; c++ {
				x := (2*c + 1) * 64 / 6
				pixel := dst.Pixels[12*dst.Stride+x*4:]
				if int(pixel[2-c]) < 100 || int(pixel[2-c]) <= int(pixel[(3-c)%3])+40 {
					t.Fatalf("BGRA channel %d: %v", c, pixel[:4])
				}
			}
		}
		binary.LittleEndian.PutUint16(src.Pixels, 0x7c00)
		if !software {
			reference = append([]byte(nil), dst.Pixels...)
		} else {
			for i, value := range dst.Pixels {
				if delta := int(value) - int(reference[i]); delta < -2 || delta > 2 {
					t.Fatalf("硬件和 WARP 差异过大：byte=%d %d/%d", i, value, reference[i])
				}
			}
		}
		if p.Process(src, dst) != frame.ErrInvalid {
			t.Fatal("infinite pixel accepted")
		}
		p.Close()
		p.Close()
		if p.Process(src, dst) != ErrClosed {
			t.Fatal("closed processor accepted input")
		}
	}
}
