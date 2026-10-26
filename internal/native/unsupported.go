//go:build !cgo || android || ios || !((windows && amd64) || (linux && amd64) || (darwin && arm64))

package native

import "termous/video/frame"

const Supported = false

type Encoder struct{}

func New(Config) (*Encoder, error)                                  { return nil, ErrUnsupported }
func (*Encoder) Close()                                             {}
func (*Encoder) UpdateRate(int, int) error                          { return ErrUnsupported }
func (*Encoder) EncodeBGRA(frame.BGRA, bool, int64) (Output, error) { return Output{}, ErrUnsupported }
func (*Encoder) EncodeI420(frame.I420, bool, int64) (Output, error) { return Output{}, ErrUnsupported }
func Convert(frame.BGRA, frame.I420) error                          { return ErrUnsupported }
func Scale(frame.I420, frame.I420) error                            { return ErrUnsupported }
