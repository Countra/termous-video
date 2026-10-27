package frame

import "math"

// RGBA16F 使用小端 IEEE binary16、线性 BT.709/scRGB，1.0 恒为 80 nit。
// PeakNits 为已知的显示参考峰值，零表示未知；不代表内容 MaxCLL。
type RGBA16F struct {
	Size
	Pixels   []byte
	Stride   int
	PeakNits float32
}

func (f RGBA16F) Validate() error {
	if f.Size.Validate() != nil || !validPlane(f.Pixels, f.Stride, f.Width*8, f.Height) ||
		math.IsNaN(float64(f.PeakNits)) || math.IsInf(float64(f.PeakNits), 0) || f.PeakNits < 0 || f.PeakNits > 10000 {
		return ErrInvalid
	}
	return nil
}
