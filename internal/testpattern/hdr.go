package testpattern

import (
	"encoding/binary"
	"math"
	"termous/video/frame"
)

// HDR 使用相同动态布局，线性值覆盖 0–4，包含桌面白色以上的高光。
func HDR(dst frame.RGBA16F, scratch frame.BGRA, sequence int) {
	Desktop(scratch, sequence)
	for y := 0; y < dst.Height; y++ {
		for x := 0; x < dst.Width; x++ {
			s, d := y*scratch.Stride+x*4, y*dst.Stride+x*8
			binary.LittleEndian.PutUint16(dst.Pixels[d:], linearHalf[scratch.Pixels[s+2]])
			binary.LittleEndian.PutUint16(dst.Pixels[d+2:], linearHalf[scratch.Pixels[s+1]])
			binary.LittleEndian.PutUint16(dst.Pixels[d+4:], linearHalf[scratch.Pixels[s]])
			binary.LittleEndian.PutUint16(dst.Pixels[d+6:], 0x3c00)
		}
	}
}

var linearHalf = func() [256]uint16 {
	var values [256]uint16
	for i := 1; i < len(values); i++ {
		m, e := math.Frexp(float64(i) / 64)
		values[i] = uint16((e+14)*1024 + int(math.RoundToEven((m*2-1)*1024)))
	}
	return values
}()
