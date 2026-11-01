package color

import (
	"errors"
	"sync/atomic"
	"termous/video/frame"
	"termous/video/internal/colornative"
)

var ErrTicket = errors.New("video: stale color task")
var processorGeneration atomic.Uint64

type Resources = colornative.Resources

// Ticket 同时标识资源代次与任务；不可跨处理器或重建使用。
type Ticket struct{ Generation, Sequence uint64 }
type asyncState struct {
	size       frame.Size
	generation uint64
	tasks      map[Ticket]bool
}

// AsyncResources 不分配槽位；调用方先预约原生主存，再调用 PrepareAsync。
func (p *Processor) AsyncResources(size frame.Size) (Resources, error) {
	if err := size.Validate(); err != nil {
		return Resources{}, err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.engine == nil {
		return Resources{}, ErrClosed
	}
	return p.engine.Plan(size)
}

func (p *Processor) PrepareAsync(size frame.Size) error {
	if err := size.Validate(); err != nil {
		return err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.engine == nil {
		return ErrClosed
	}
	if len(p.async.tasks) != 0 {
		return ErrBusy
	}
	if err := p.engine.Prepare(size, p.options.MeasureStages); err != nil {
		return err
	}
	p.async = asyncState{size: size, generation: processorGeneration.Add(1), tasks: make(map[Ticket]bool, 2)}
	return nil
}

// Submit 返回后允许释放输入；输出内存由调用方提前持有，收取时才借给原生层。
func (p *Processor) Submit(src frame.RGBA16F) (Ticket, error) {
	if src.Validate() != nil || src.Stride%8 != 0 {
		return Ticket{}, frame.ErrInvalid
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.engine == nil {
		return Ticket{}, ErrClosed
	}
	if p.async.generation == 0 || src.Size != p.async.size {
		return Ticket{}, frame.ErrInvalid
	}
	if len(p.async.tasks) >= 2 {
		return Ticket{}, ErrBusy
	}
	p.sequence++
	t := Ticket{p.async.generation, p.sequence}
	if err := p.engine.Submit(src, t.Sequence); err != nil {
		return Ticket{}, err
	}
	p.async.tasks[t] = false
	return t, nil
}

func (p *Processor) Ready(t Ticket) (bool, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if _, ok := p.async.tasks[t]; !ok {
		return false, ErrTicket
	}
	err := p.engine.Ready(t.Sequence)
	if errors.Is(err, ErrBusy) {
		return false, nil
	}
	return err == nil, err
}

// Discard 仅停止交付；仍需等待完成并 Collect，或 Close 安全收尾后才能释放资源。
func (p *Processor) Discard(t Ticket) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if _, ok := p.async.tasks[t]; !ok {
		return ErrTicket
	}
	if err := p.engine.Discard(t.Sequence); err != nil {
		return err
	}
	p.async.tasks[t] = true
	return nil
}

func (p *Processor) Collect(t Ticket, dst frame.BGRA) (Timings, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	discarded, ok := p.async.tasks[t]
	if !ok {
		return Timings{}, ErrTicket
	}
	if !discarded && (dst.Validate() != nil || dst.Size != p.async.size || dst.Stride%4 != 0) {
		return Timings{}, frame.ErrInvalid
	}
	timings, err := p.engine.Collect(t.Sequence, dst)
	if err == nil {
		delete(p.async.tasks, t)
	}
	return timings, err
}

// RecoverAsync 只对明确设备失效恢复一次；返回前收尾全部旧任务，旧令牌立即失效。
func (p *Processor) RecoverAsync() (bool, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.engine == nil || !p.engine.Failed() || p.rebuilt {
		return false, nil
	}
	p.rebuilt = true
	p.engine.Close()
	p.async = asyncState{}
	var err error
	p.engine, err = colornative.New(p.options.Software)
	p.failure = err
	return true, err
}
