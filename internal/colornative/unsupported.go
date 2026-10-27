//go:build !cgo || android || ios || !((windows && amd64) || (linux && amd64) || (darwin && arm64))

package colornative

import "termous/video/frame"

const Supported = false

type Processor struct{}

func New(bool) (*Processor, error)                         { return nil, ErrUnavailable }
func (*Processor) Close()                                  {}
func (*Processor) Backend() string                         { return "unavailable" }
func (*Processor) Failed() bool                            { return true }
func (*Processor) Process(frame.RGBA16F, frame.BGRA) error { return ErrUnavailable }
