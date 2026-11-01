// Package h264 封装同步屏幕内容编码，不负责观看会话、网络预算或帧调度。
package h264

import (
	"sync"
	"termous/video/frame"
	"termous/video/internal/limits"
	"termous/video/internal/native"
	"time"
)

var (
	ErrUnsupported         = native.ErrUnsupported
	ErrClosed              = native.ErrClosed
	ErrInvalidConfig       = native.ErrInvalidConfig
	ErrNative              = native.ErrNative
	ErrUnusable            = native.ErrUnusable
	ErrReconfigureRequired = native.ErrReconfigureRequired
)

type Level int

const (
	Level31 Level = 31
	Level32 Level = 32
	Level40 Level = 40
	Level41 Level = 41
	Level42 Level = 42
	Level50 Level = 50
	Level51 Level = 51
)

type Matrix int

const (
	// Matrix601 保留既有 BGRA 转换的有限范围语义。
	Matrix601 Matrix = 0
	Matrix709 Matrix = 709
)

// RateControl 的 Bitrate 单位为 bit/s，FPS 为编码帧率上限，不负责调用方调度。
type RateControl struct{ Bitrate, FPS int }
type Config struct {
	Size   frame.Size
	Rate   RateControl
	Level  Level
	Matrix Matrix
	// Threads 为零时采用当前 CPU 预算，显式值限制在 1–16；实际值受切片行数约束。
	Threads int
}
type Options struct {
	// MeasureStages 仅在显式诊断时记录转换和编码耗时。
	MeasureStages bool
	Keyframe      bool
	TimestampMS   int64
	// Rate 与本帧编码一起提交，仅允许同 FPS 的码率更新。
	Rate *RateControl
}
type Result struct {
	// QPPlusOne 为本帧全局率控 QP 加一（1～70）；零表示未知，不代表码流切片 QP 或画质评分。
	QPPlusOne                    uint8
	ConversionTime, EncodingTime time.Duration
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
	return Capabilities{Supported: native.Supported, MinSize: frame.Size{Width: 16, Height: 16}, MaxSize: frame.Size{Width: 2560, Height: 1440}, MinBitrate: 100_000, MaxBitrate: limits.MaxBitrate, MaxFPS: limits.MaxFPS, Levels: []Level{Level31, Level32, Level40, Level41, Level42, Level50, Level51}}
}

// Validate 同时验证尺寸、宏块率和码率；MaxSize 的长短边允许互换。
func (c Config) Validate() error { return c.native().Validate() }
func (c Config) native() native.Config {
	return native.Config{Width: c.Size.Width, Height: c.Size.Height, Bitrate: c.Rate.Bitrate, FPS: c.Rate.FPS, Level: int(c.Level), Matrix: int(c.Matrix), Threads: c.Threads}
}
func MinimumLevel(size frame.Size, rate RateControl) (Level, error) {
	level := limits.Minimum(size.Width, size.Height, rate.Bitrate, rate.FPS)
	if level == 0 {
		return 0, ErrInvalidConfig
	}
	return Level(level), nil
}

// Encoder 的调用可并发进入，但原生对象始终串行访问；Close 等待在途调用完成。
type Encoder struct {
	mu     sync.Mutex
	engine *native.Encoder
	config Config
	info   Info
}

// Info 仅描述创建时确认的实现参数，不把请求预算当作实测码率。
type Info struct {
	Implementation, Version, Preset string
	Threads                         int
}

func (e *Encoder) Info() Info { return e.info }

func New(config Config) (*Encoder, error) {
	c := config.native()
	if err := c.Validate(); err != nil {
		return nil, err
	}
	e, err := native.New(c)
	if err != nil {
		return nil, err
	}
	info, err := e.Info()
	if err != nil {
		e.Close()
		return nil, err
	}
	return &Encoder{engine: e, config: config, info: Info(info)}, nil
}

func (e *Encoder) options(o Options) (native.Options, error) {
	result := native.Options{MeasureStages: o.MeasureStages, Keyframe: o.Keyframe, TimestampMS: o.TimestampMS}
	if o.Rate == nil {
		return result, nil
	}
	candidate := e.config
	candidate.Rate = *o.Rate
	if candidate.Validate() != nil {
		return result, ErrInvalidConfig
	}
	if candidate.Rate.FPS != e.config.Rate.FPS {
		return result, ErrReconfigureRequired
	}
	result.Rate = &native.RateControl{Bitrate: candidate.Rate.Bitrate, FPS: candidate.Rate.FPS}
	return result, nil
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
	o, err := e.options(options)
	if err != nil {
		return Result{}, err
	}
	out, err := e.engine.EncodeBGRA(src, o)
	if err == nil && o.Rate != nil {
		e.config.Rate = RateControl(*o.Rate)
	}
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
	o, err := e.options(options)
	if err != nil {
		return Result{}, err
	}
	out, err := e.engine.EncodeI420(src, o)
	if err == nil && o.Rate != nil {
		e.config.Rate = RateControl(*o.Rate)
	}
	return e.result(out, options), err
}

func (e *Encoder) result(out native.Output, options Options) Result {
	return Result{QPPlusOne: out.QPPlusOne, ConversionTime: out.ConversionTime, EncodingTime: out.EncodingTime, Data: out.Data, Keyframe: out.Keyframe, Skipped: out.Skipped, Size: e.config.Size, TimestampMS: options.TimestampMS}
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
