// Package color 使用 libplacebo 将原始 HDR 帧转换成共享的 SDR 帧。
package color

import (
	"sync"
	"termous/video/frame"
	"termous/video/internal/colornative"
)

var (
	ErrUnavailable = colornative.ErrUnavailable
	ErrFailed      = colornative.ErrFailed
	ErrClosed      = colornative.ErrClosed
)

type Options struct {
	// Software 在 Windows 强制使用系统 WARP，其他平台返回不可用。
	// 默认模式允许 libplacebo 选择系统已有的软件设备，不安装或分发渲染器。
	Software bool
}
type Capabilities struct{ Compiled bool }

func QueryCapabilities() Capabilities { return Capabilities{Compiled: colornative.Supported} }

// Processor 串行复用设备和纹理；创建失败不会阻止其他 SDR 来源工作。
type Processor struct {
	mu      sync.Mutex
	engine  *colornative.Processor
	options Options
	rebuilt bool
	failure error
}

func New(options Options) (*Processor, error) {
	e, err := colornative.New(options.Software)
	if err != nil {
		return nil, err
	}
	return &Processor{engine: e, options: options}, nil
}
func (p *Processor) Backend() string {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.engine == nil {
		return "unavailable"
	}
	return p.engine.Backend()
}

// Process 同步借用输入与目标，成功输出为 sRGB/BGRA8，全范围，不改变尺寸。
// GPU 传输要求输入步长按 RGBA16F 像素（8 字节）、输出步长按 BGRA8 像素（4 字节）对齐。
// 失败时目标内容不可使用；设备失败最多重建一次，不返回部分画面。
func (p *Processor) Process(src frame.RGBA16F, dst frame.BGRA) error {
	if src.Validate() != nil || dst.Validate() != nil || src.Size != dst.Size || src.Stride%8 != 0 || dst.Stride%4 != 0 {
		return frame.ErrInvalid
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.engine == nil {
		if p.failure != nil {
			return p.failure
		}
		return ErrClosed
	}
	err := p.engine.Process(src, dst)
	if err == ErrFailed && p.engine.Failed() && !p.rebuilt {
		p.rebuilt = true
		p.engine.Close()
		p.engine, err = colornative.New(p.options.Software)
		p.failure = err
		if err == nil {
			err = p.engine.Process(src, dst)
		}
	}
	return err
}
func (p *Processor) Close() {
	if p == nil {
		return
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	p.failure = nil
	if p.engine != nil {
		p.engine.Close()
		p.engine = nil
	}
}
