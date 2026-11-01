//go:build !cgo || android || ios || !((windows && amd64) || (linux && amd64) || (darwin && arm64))

package colornative

import "termous/video/frame"

const Supported = false

type Processor struct{}

func New(bool) (*Processor, error)                                   { return nil, ErrUnavailable }
func (*Processor) Close()                                            {}
func (*Processor) Backend() string                                   { return "unavailable" }
func (*Processor) Device() string                                    { return "unavailable" }
func (*Processor) Failed() bool                                      { return true }
func (*Processor) Process(frame.RGBA16F, frame.BGRA, *Timings) error { return ErrUnavailable }
func (*Processor) Plan(frame.Size) (Resources, error)                { return Resources{}, ErrUnavailable }
func (*Processor) Prepare(frame.Size, bool) error                    { return ErrUnavailable }
func (*Processor) Submit(frame.RGBA16F, uint64) error                { return ErrUnavailable }
func (*Processor) Ready(uint64) error                                { return ErrUnavailable }
func (*Processor) Discard(uint64) error                              { return ErrUnavailable }
func (*Processor) Collect(uint64, frame.BGRA) (Timings, error)       { return Timings{}, ErrUnavailable }
