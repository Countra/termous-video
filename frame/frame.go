// Package frame 定义同步借用的 CPU 帧；调用期间不得修改或释放缓冲。
package frame

import "errors"

const MaxPixels = 16 * 1024 * 1024

var ErrInvalid = errors.New("video: invalid frame")

type Size struct{ Width, Height int }

func (s Size) Validate() error {
	if s.Width < 1 || s.Height < 1 || uint64(s.Width)*uint64(s.Height) > MaxPixels || s.Width > MaxPixels || s.Height > MaxPixels {
		return ErrInvalid
	}
	return nil
}

type BGRA struct {
	Size
	Pixels []byte
	// Stride 为相邻两行起点间的字节数；最后一行可不含尾部填充。
	Stride int
}

func (f BGRA) Validate() error {
	if f.Size.Validate() != nil || !validPlane(f.Pixels, f.Stride, f.Width*4, f.Height) {
		return ErrInvalid
	}
	return nil
}

// I420 使用 BT.601 有限范围；奇数尺寸的色度平面按向上取整计算。
type I420 struct {
	Size
	Y, U, V                   []byte
	YStride, UStride, VStride int
}

func (f I420) Validate() error {
	if f.Size.Validate() != nil {
		return ErrInvalid
	}
	cw, ch := (f.Width+1)/2, (f.Height+1)/2
	if !validPlane(f.Y, f.YStride, f.Width, f.Height) || !validPlane(f.U, f.UStride, cw, ch) || !validPlane(f.V, f.VStride, cw, ch) {
		return ErrInvalid
	}
	return nil
}

func NewI420(size Size) (I420, error) {
	if err := size.Validate(); err != nil {
		return I420{}, err
	}
	y, c := size.Width*size.Height, ((size.Width+1)/2)*((size.Height+1)/2)
	data := make([]byte, y+2*c)
	return I420{Size: size, Y: data[:y:y], U: data[y : y+c : y+c], V: data[y+c:], YStride: size.Width, UStride: (size.Width + 1) / 2, VStride: (size.Width + 1) / 2}, nil
}

func validPlane(data []byte, stride, row, height int) bool {
	return stride >= row && stride <= 1<<31-1 && uint64(len(data)) >= uint64(height-1)*uint64(stride)+uint64(row)
}
