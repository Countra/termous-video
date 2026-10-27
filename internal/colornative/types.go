package colornative

import "errors"

var (
	ErrUnavailable = errors.New("video: HDR conversion backend unavailable")
	ErrFailed      = errors.New("video: HDR conversion failed")
	ErrClosed      = errors.New("video: color processor closed")
)
