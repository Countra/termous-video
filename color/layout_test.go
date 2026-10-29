package color

import (
	"bytes"
	"termous/video/frame"
	"testing"
)

func TestDesktopTransferLayout(t *testing.T) {
	p := newTestProcessor(t, false)
	src, expected := fixtureFrame([][3]float64{{.1, .2, .3}, {.5, .5, .5}, {1, 1, 1}}, 200)
	if err := p.Process(src, expected); err != nil {
		t.Fatal(err)
	}
	// 行间填充不属于像素，最后一行无需填充；尾部哨兵检查下载没有越界。
	padded := src
	padded.Stride += 8
	padded.Pixels = bytes.Repeat([]byte{0xff}, padded.Stride*(src.Height-1)+src.Stride)
	for y := 0; y < src.Height; y++ {
		copy(padded.Pixels[y*padded.Stride:], src.Pixels[y*src.Stride:(y+1)*src.Stride])
	}
	dst := frame.BGRA{Size: src.Size, Stride: expected.Stride + 4}
	length := dst.Stride*(dst.Height-1) + expected.Stride
	storage := bytes.Repeat([]byte{0xa5}, length+16)
	dst.Pixels = storage[:length:length]
	if err := p.Process(padded, dst); err != nil {
		t.Fatal(err)
	}
	for y := 0; y < dst.Height; y++ {
		if !bytes.Equal(dst.Pixels[y*dst.Stride:y*dst.Stride+expected.Stride], expected.Pixels[y*expected.Stride:(y+1)*expected.Stride]) {
			t.Fatalf("row %d differs from packed output", y)
		}
	}
	if !bytes.Equal(storage[length:], bytes.Repeat([]byte{0xa5}, 16)) {
		t.Fatal("download wrote beyond the final row")
	}
	for _, tc := range []struct {
		name       string
		srcPadding int
		dstPadding int
	}{
		{"input-row", 1, 0},
		{"output-row", 0, 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			invalidSrc, invalidDst := src, expected
			invalidSrc.Stride += tc.srcPadding
			invalidSrc.Pixels = make([]byte, invalidSrc.Stride*invalidSrc.Height)
			invalidDst.Stride += tc.dstPadding
			invalidDst.Pixels = bytes.Repeat([]byte{0xa5}, invalidDst.Stride*invalidDst.Height)
			if err := p.Process(invalidSrc, invalidDst); err != frame.ErrInvalid {
				t.Fatalf("invalid layout: %v", err)
			}
			if !bytes.Equal(invalidDst.Pixels, bytes.Repeat([]byte{0xa5}, len(invalidDst.Pixels))) {
				t.Fatal("rejected layout modified output")
			}
		})
	}
	if err := p.Process(src, expected); err != nil {
		t.Fatalf("valid frame after rejected layout: %v", err)
	}
}
