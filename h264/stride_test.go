//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package h264

import (
	"bytes"
	"testing"

	"termous/video/frame"
	"termous/video/internal/native"
)

func TestI420IndependentChromaStrides(t *testing.T) {
	c := testConfig()
	cw, ch := c.Size.Width/2, c.Size.Height/2
	for _, tc := range []struct {
		name             string
		uStride, vStride int
	}{
		{"larger_v", cw, cw*2 + 5},
		{"larger_u", cw*2 + 5, cw},
		{"equal_padding", cw + 11, cw + 11},
	} {
		t.Run(tc.name, func(t *testing.T) {
			e, err := New(c)
			if err != nil {
				t.Fatal(err)
			}
			defer e.Close()
			// 填充区故意使用不同颜色，且末行不分配尾部填充。
			plane := func(width, height, stride int, value byte) []byte {
				data := bytes.Repeat([]byte{8}, (height-1)*stride+width)
				for row := 0; row < height; row++ {
					for x := 0; x < width; x++ {
						data[row*stride+x] = value
					}
				}
				return data
			}
			f := frame.I420{Size: c.Size, YStride: c.Size.Width + 7, UStride: tc.uStride, VStride: tc.vStride}
			f.Y = plane(f.Width, f.Height, f.YStride, 82)
			f.U = plane(cw, ch, f.UStride, 90)
			f.V = plane(cw, ch, f.VStride, 240)
			out, err := e.EncodeI420(f, Options{Keyframe: true})
			if err != nil {
				t.Fatal(err)
			}
			sample, err := native.TestDecode(out.Data)
			if err != nil || sample.Width != f.Width || sample.Height != f.Height {
				t.Fatalf("decoded %+v: %v", sample, err)
			}
			for i, expected := range [3]int{82, 90, 240} {
				if delta := sample.YUV[i] - expected; delta < -4 || delta > 4 {
					t.Fatalf("last-row YUV = %v, want approximately [82 90 240]", sample.YUV)
				}
			}
		})
	}
}
