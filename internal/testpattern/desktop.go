// Package testpattern 提供可重复的动态桌面素材，不依赖采集设备或编解码器。
package testpattern

import "termous/video/frame"

// Desktop 与原标量公式逐像素一致；预计算周期图案，避免造图占满基准时间。
func Desktop(dst frame.BGRA, sequence int) {
	wx := (sequence * 13) % max(1, dst.Width*3/4)
	left := dst.Width/2 + 1
	for y := 0; y < dst.Height; y++ {
		row := dst.Pixels[y*dst.Stride:][:dst.Width*4]
		sy := y + sequence*3
		line := desktopText[sy%15][:]
		if sy%28 >= 14 {
			line = desktopWhite[:]
		}
		offset := (sequence * 7) % 480 * 4
		for filled := 0; filled < left*4; {
			n := copy(row[filled:left*4], line[offset:])
			filled += n
			offset = 0
		}
		phase := (left + sequence*7) % len(desktopTexture)
		for x := left; x < dst.Width; x++ {
			pixel := desktopTexture[phase]
			i := x * 4
			row[i], row[i+1], row[i+2], row[i+3] = pixel[0]+byte(sy/5), pixel[1]+byte(sy/2), pixel[2]+byte(sy/9), 255
			phase++
			if phase == len(desktopTexture) {
				phase = 0
			}
		}
		if y > dst.Height/3 && y < dst.Height*2/3 {
			for x := wx; x < min(dst.Width, wx+dst.Width/4); x++ {
				i := x * 4
				row[i], row[i+1], row[i+2] = byte((x-wx)*3), byte(y*2), byte((x-wx)^y)
			}
		}
	}
}

var desktopText = func() [15][480 * 4]byte {
	var lines [15][480 * 4]byte
	for y := range lines {
		for x := 0; x < 480; x++ {
			v := byte(224)
			if x%96 < 76 && (x/4+y/3)%5 != 0 {
				v = 40
			}
			i := x * 4
			lines[y][i], lines[y][i+1], lines[y][i+2], lines[y][i+3] = v, v, v, 255
		}
	}
	return lines
}()

var desktopWhite = func() [480 * 4]byte {
	var line [480 * 4]byte
	for i := 0; i < len(line); i += 4 {
		line[i], line[i+1], line[i+2], line[i+3] = 224, 224, 224, 255
	}
	return line
}()

// 三个通道分别以 3×256、7×256、5×256 为周期，共同周期为 26880。
var desktopTexture = func() [26880][3]byte {
	var values [26880][3]byte
	for x := range values {
		values[x] = [3]byte{byte(x / 3), byte(x / 7), byte(x / 5)}
	}
	return values
}()
