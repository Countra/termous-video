// Package buffer 检查同步原生写入的缓冲别名，防止原地转换破坏尚未读取的数据。
package buffer

import "unsafe"

func Overlap(a, b []byte) bool {
	if len(a) == 0 || len(b) == 0 {
		return false
	}
	x, y := uintptr(unsafe.Pointer(unsafe.SliceData(a))), uintptr(unsafe.Pointer(unsafe.SliceData(b)))
	if x <= y {
		return y-x < uintptr(len(a))
	}
	return x-y < uintptr(len(b))
}

func Distinct(planes ...[]byte) bool {
	for i, a := range planes {
		for _, b := range planes[i+1:] {
			if Overlap(a, b) {
				return false
			}
		}
	}
	return true
}
