package color

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"runtime"
	"termous/video/frame"
	"testing"
	"time"
)

func awaitColor(t *testing.T, p *Processor, ticket Ticket, dst frame.BGRA) Timings {
	t.Helper()
	deadline := time.Now().Add(10 * time.Second)
	for time.Now().Before(deadline) {
		ready, err := p.Ready(ticket)
		if err != nil {
			t.Fatal(err)
		}
		if ready {
			stages, err := p.Collect(ticket, dst)
			if errors.Is(err, ErrBusy) {
				continue
			}
			if err != nil {
				t.Fatal(err)
			}
			return stages
		}
		time.Sleep(time.Millisecond)
	}
	t.Fatal("异步读回未完成")
	return Timings{}
}

func TestAsyncReadbackOwnershipAndPixels(t *testing.T) {
	for _, software := range []bool{false, true} {
		if software && runtime.GOOS != "windows" {
			continue
		}
		t.Run(fmt.Sprint(software), func(t *testing.T) {
			p := newTestProcessor(t, software)
			size := frame.Size{Width: 65, Height: 17}
			src := frame.RGBA16F{Size: size, SDRWhiteNits: 200, Stride: size.Width*8 + 16, Pixels: make([]byte, (size.Width*8+16)*size.Height)}
			output := func() frame.BGRA {
				return frame.BGRA{Size: size, Stride: size.Width*4 + 12, Pixels: make([]byte, (size.Width*4+12)*size.Height)}
			}
			values := []uint16{0, 0x3400, 0x3c00, 0x4100, 0x4800, 0xb400, 0x7bff, 0x3800}
			for pattern := 0; pattern < 8; pattern++ {
				for y := 0; y < size.Height; y++ {
					for x := 0; x < size.Width; x++ {
						for c := 0; c < 4; c++ {
							v := values[(x+y+c+pattern)%len(values)]
							if c == 3 {
								v = 0x3c00
							}
							binary.LittleEndian.PutUint16(src.Pixels[y*src.Stride+x*8+c*2:], v)
						}
					}
				}
				want := output()
				if err := p.Process(src, want); err != nil {
					t.Fatal(err)
				}
				if err := p.PrepareAsync(size); err != nil {
					t.Fatal(err)
				}
				a, err := p.Submit(src)
				if err != nil {
					t.Fatal(err)
				}
				b, err := p.Submit(src)
				if err != nil {
					t.Fatal(err)
				}
				if _, err = p.Submit(src); !errors.Is(err, ErrBusy) {
					t.Fatal("第三槽被接受", err)
				}
				if err = p.Process(src, output()); !errors.Is(err, ErrBusy) {
					t.Fatal("在途时混用同步调用", err)
				}
				clear(src.Pixels)
				runtime.GC()
				got := output()
				awaitColor(t, p, a, got)
				if !bytes.Equal(want.Pixels, got.Pixels) {
					t.Fatalf("异步像素或输入所有权错误 pattern=%d", pattern)
				}
				if err = p.Discard(b); err != nil {
					t.Fatal(err)
				}
				awaitColor(t, p, b, frame.BGRA{})
				if _, err = p.Ready(a); !errors.Is(err, ErrTicket) {
					t.Fatal("旧令牌再次使用", err)
				}
			}
		})
	}
}

func TestAsyncRejectsInvalidAndCloseInflight(t *testing.T) {
	p := newTestProcessor(t, false)
	if _, err := p.AsyncResources(frame.Size{Width: frame.MaxPixels, Height: 1}); !errors.Is(err, ErrUnavailable) {
		t.Fatal("超出纹理边长未安全拒绝", err)
	}
	size := frame.Size{Width: 16, Height: 16}
	src := frame.RGBA16F{Size: size, SDRWhiteNits: 80, Stride: 128, Pixels: make([]byte, 2048)}
	if err := p.PrepareAsync(size); err != nil {
		t.Fatal(err)
	}
	for _, special := range []uint16{0x7c00, 0xfc00, 0x7e00} {
		binary.LittleEndian.PutUint16(src.Pixels, special)
		if _, err := p.Submit(src); !errors.Is(err, frame.ErrInvalid) {
			t.Fatal(err)
		}
	}
	clear(src.Pixels)
	a, err := p.Submit(src)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = p.Submit(src); err != nil {
		t.Fatal(err)
	}
	p.Close()
	p.Close()
	if _, err = p.Ready(a); !errors.Is(err, ErrTicket) {
		t.Fatal("关闭后令牌有效", err)
	}
}
