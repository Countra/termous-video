package convert

import (
	"bytes"
	"errors"
	"termous/video/frame"
	"testing"
)

func TestConvertPaddedBGRAAndScale(t *testing.T) {
	if !Supported() {
		t.Skip("native SDK unavailable")
	}
	src := frame.BGRA{Size: frame.Size{Width: 3, Height: 3}, Stride: 16, Pixels: bytes.Repeat([]byte{0xaa}, 44)}
	for y := 0; y < 3; y++ {
		for x := 0; x < 3; x++ {
			p := src.Pixels[y*16+x*4:]
			p[0] = 0
			p[1] = 0
			p[2] = 255
			p[3] = 255
		}
	}
	before := bytes.Clone(src.Pixels)
	dst, _ := frame.NewI420(src.Size)
	if err := BGRAToI420(src, dst); err != nil {
		t.Fatal(err)
	}
	// 红色对应 BT.601 有限范围的 Y≈82、U≈90、V≈240，允许整数舍入。
	for _, sample := range []struct {
		data []byte
		want byte
	}{{dst.Y, 82}, {dst.U, 90}, {dst.V, 240}} {
		for _, v := range sample.data {
			if int(v) < int(sample.want)-1 || int(v) > int(sample.want)+1 {
				t.Fatalf("unexpected color: %d want %d", v, sample.want)
			}
		}
	}
	if !bytes.Equal(src.Pixels, before) {
		t.Fatal("input modified")
	}
	small, _ := frame.NewI420(frame.Size{Width: 2, Height: 2})
	if err := ScaleI420(dst, small); err != nil || small.Y[0] != dst.Y[0] {
		t.Fatalf("scale: %v", err)
	}
	if err := ScaleI420(dst, dst); !errors.Is(err, frame.ErrInvalid) {
		t.Fatal("in-place scaling accepted", err)
	}
}
func TestUnsupported(t *testing.T) {
	if Supported() {
		t.Skip("native SDK available")
	}
	dst, _ := frame.NewI420(frame.Size{Width: 2, Height: 2})
	err := BGRAToI420(frame.BGRA{Size: dst.Size, Pixels: make([]byte, 16), Stride: 8}, dst)
	if !errors.Is(err, ErrUnsupported) {
		t.Fatal(err)
	}
}

func TestReusablePaddedDestination(t *testing.T) {
	if !Supported() {
		t.Skip("native SDK unavailable")
	}
	src := frame.BGRA{Size: frame.Size{Width: 2, Height: 2}, Stride: 8, Pixels: make([]byte, 16)}
	dst := frame.I420{Size: src.Size, YStride: 4, UStride: 2, VStride: 2,
		Y: bytes.Repeat([]byte{0xaa}, 8), U: bytes.Repeat([]byte{0xaa}, 2), V: bytes.Repeat([]byte{0xaa}, 2)}
	for _, value := range []byte{0, 255, 0} {
		for i := range src.Pixels {
			src.Pixels[i] = value
		}
		if err := BGRAToI420(src, dst); err != nil {
			t.Fatal(err)
		}
		want := byte(16)
		if value == 255 {
			want = 235
		}
		if dst.Y[0] != want || dst.Y[4] != want || dst.U[0] != 128 || dst.V[0] != 128 {
			t.Fatal("reused output contains stale or incorrect pixels")
		}
		if dst.Y[2] != 0xaa || dst.Y[3] != 0xaa || dst.Y[6] != 0xaa || dst.Y[7] != 0xaa || dst.U[1] != 0xaa || dst.V[1] != 0xaa {
			t.Fatal("conversion wrote beyond the active row")
		}
	}
}
