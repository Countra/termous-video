package native

import (
	"errors"
	"termous/video/internal/limits"
	"time"
)

var (
	ErrUnsupported         = errors.New("video: native encoding is unavailable")
	ErrClosed              = errors.New("video: encoder is closed")
	ErrInvalidConfig       = errors.New("video: invalid encoder configuration")
	ErrNative              = errors.New("video: native operation failed")
	ErrUnusable            = errors.New("video: encoder state is unusable")
	ErrReconfigureRequired = errors.New("video: frame rate change requires a new encoder")
)

type Config struct{ Width, Height, Bitrate, FPS, Level, Matrix, Threads int }
type RateControl struct{ Bitrate, FPS int }
type Options struct {
	MeasureStages bool
	Keyframe      bool
	TimestampMS   int64
	Rate          *RateControl
}
type Info struct {
	Implementation, Version, Preset string
	Threads                         int
}
type Output struct {
	QPPlusOne                    uint8
	ConversionTime, EncodingTime time.Duration
	Data                         []byte
	Keyframe, Skipped            bool
}

func (c Config) Validate() error {
	if !limits.Valid(c.Width, c.Height, c.Bitrate, c.FPS, c.Level) || (c.Matrix != 0 && c.Matrix != 709) || c.Threads < 0 || c.Threads > 16 {
		return ErrInvalidConfig
	}
	return nil
}
