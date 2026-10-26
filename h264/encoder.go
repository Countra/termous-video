// Package h264 封装同步屏幕内容编码，不负责观看会话、网络预算或帧调度。
package h264

import (
	"sync"
	"termous/video/frame"
	"termous/video/internal/native"
)

var (
	ErrUnsupported   = native.ErrUnsupported
	ErrClosed        = native.ErrClosed
	ErrInvalidConfig = native.ErrInvalidConfig
	ErrNative        = native.ErrNative
	ErrUnusable      = native.ErrUnusable
)

type Level int

const (
	Level31 Level = 31
	Level40 Level = 40
)

// RateControl 的 Bitrate 单位为 bit/s，FPS 为编码帧率上限，不负责调用方调度。
type RateControl struct{ Bitrate, FPS int }
type Config struct {
	Size  frame.Size
	Rate  RateControl
	Level Level
}
type Options struct {
	Keyframe    bool
	TimestampMS int64
}
type Result struct {
	// Data 为独立的 Annex-B 数据；Skipped 为真时没有输出帧。
	Data              []byte
	Keyframe, Skipped bool
	Size              frame.Size
	TimestampMS       int64
}
type Capabilities struct {
	Supported                      bool
	MinSize, MaxSize               frame.Size
	MinBitrate, MaxBitrate, MaxFPS int
	Levels                         []Level
}

func QueryCapabilities() Capabilities {
	return Capabilities{Supported: native.Supported, MinSize: frame.Size{Width: 16, Height: 16}, MaxSize: frame.Size{Width: 1920, Height: 1080}, MinBitrate: 100_000, MaxBitrate: 8_000_000, MaxFPS: 30, Levels: []Level{Level31, Level40}}
}

// Encoder 的调用可并发进入，但原生对象始终串行访问；Close 等待在途调用完成。
type Encoder struct {
	mu     sync.Mutex
	engine *native.Encoder
	config Config
}

func New(config Config) (*Encoder, error) {
	c := native.Config{Width: config.Size.Width, Height: config.Size.Height, Bitrate: config.Rate.Bitrate, FPS: config.Rate.FPS, Level: int(config.Level)}
	if err := c.Validate(); err != nil {
		return nil, err
	}
	e, err := native.New(c)
	if err != nil {
		return nil, err
	}
	return &Encoder{engine: e, config: config}, nil
}

func (e *Encoder) UpdateRate(rate RateControl) error {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.engine == nil {
		return ErrClosed
	}
	if !native.ValidRate(rate.Bitrate, rate.FPS) {
		return ErrInvalidConfig
	}
	if err := e.engine.UpdateRate(rate.Bitrate, rate.FPS); err != nil {
		return err
	}
	e.config.Rate = rate
	return nil
}

func (e *Encoder) EncodeBGRA(src frame.BGRA, options Options) (Result, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.engine == nil {
		return Result{}, ErrClosed
	}
	if err := src.Validate(); err != nil {
		return Result{}, err
	}
	if options.TimestampMS < 0 {
		return Result{}, frame.ErrInvalid
	}
	out, err := e.engine.EncodeBGRA(src, options.Keyframe, options.TimestampMS)
	return e.result(out, options), err
}

func (e *Encoder) EncodeI420(src frame.I420, options Options) (Result, error) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.engine == nil {
		return Result{}, ErrClosed
	}
	if src.Validate() != nil || src.Size != e.config.Size || options.TimestampMS < 0 {
		return Result{}, frame.ErrInvalid
	}
	out, err := e.engine.EncodeI420(src, options.Keyframe, options.TimestampMS)
	return e.result(out, options), err
}

func (e *Encoder) result(out native.Output, options Options) Result {
	return Result{Data: out.Data, Keyframe: out.Keyframe, Skipped: out.Skipped, Size: e.config.Size, TimestampMS: options.TimestampMS}
}

func (e *Encoder) Close() {
	if e == nil {
		return
	}
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.engine != nil {
		e.engine.Close()
		e.engine = nil
	}
}
