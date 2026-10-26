package native

import "errors"

var (
	ErrUnsupported   = errors.New("video: native encoding is unavailable")
	ErrClosed        = errors.New("video: encoder is closed")
	ErrInvalidConfig = errors.New("video: invalid encoder configuration")
	ErrNative        = errors.New("video: native operation failed")
	ErrUnusable      = errors.New("video: encoder state cannot be restored")
)

type Config struct{ Width, Height, Bitrate, FPS, Level int }
type Output struct {
	Data              []byte
	Keyframe, Skipped bool
}

func (c Config) Validate() error {
	if c.Width < 16 || c.Height < 16 || c.Width > 1920 || c.Height > 1080 || c.Width%2 != 0 || c.Height%2 != 0 || !ValidRate(c.Bitrate, c.FPS) || (c.Level != 31 && c.Level != 40) || (c.Level == 31 && (c.Width > 1280 || c.Height > 720)) {
		return ErrInvalidConfig
	}
	return nil
}

func ValidRate(bitrate, fps int) bool {
	return bitrate >= 100_000 && bitrate <= 8_000_000 && fps >= 1 && fps <= 30
}
