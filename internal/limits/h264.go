// Package limits 提供不依赖 cgo 的编码边界，宏块按编码尺寸向上取整。
package limits

const MaxBitrate = 100_000_000
const MaxFPS = 60

type Level struct{ ID, Frame, Rate, Bitrate int }

var Levels = [...]Level{
	{31, 3600, 108000, 14_000_000}, {32, 5120, 216000, 20_000_000},
	{40, 8192, 245760, 20_000_000}, {41, 8192, 245760, 50_000_000},
	{42, 8704, 522240, 50_000_000}, {50, 22080, 589824, MaxBitrate},
	{51, 36864, 983040, MaxBitrate},
}

func Valid(w, h, bitrate, fps, level int) bool {
	if w < 16 || h < 16 || w%2 != 0 || h%2 != 0 || max(w, h) > 2560 || min(w, h) > 1440 || bitrate < 100_000 || bitrate > MaxBitrate || fps < 1 || fps > MaxFPS {
		return false
	}
	mb := ((w + 15) / 16) * ((h + 15) / 16)
	for _, l := range Levels {
		if l.ID == level {
			return mb <= l.Frame && mb*fps <= l.Rate && bitrate <= l.Bitrate
		}
	}
	return false
}

func Minimum(w, h, bitrate, fps int) int {
	for _, l := range Levels {
		if Valid(w, h, bitrate, fps, l.ID) {
			return l.ID
		}
	}
	return 0
}
