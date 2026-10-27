package native

import (
	"errors"
	"termous/video/internal/limits"
)

var (
	ErrUnsupported   = errors.New("video: native encoding is unavailable")
	ErrClosed        = errors.New("video: encoder is closed")
	ErrInvalidConfig = errors.New("video: invalid encoder configuration")
	ErrNative        = errors.New("video: native operation failed")
	ErrUnusable      = errors.New("video: encoder state cannot be restored")
)

type Config struct{ Width, Height, Bitrate, FPS, Level, Matrix int }
type Output struct {
	Data              []byte
	Keyframe, Skipped bool
}

func (c Config) Validate() error {
	if !limits.Valid(c.Width, c.Height, c.Bitrate, c.FPS, c.Level) || (c.Matrix != 0 && c.Matrix != 709) {
		return ErrInvalidConfig
	}
	return nil
}

func ValidRate(bitrate, fps int) bool {
	return bitrate >= 100_000 && bitrate <= limits.MaxBitrate && fps >= 1 && fps <= limits.MaxFPS
}
