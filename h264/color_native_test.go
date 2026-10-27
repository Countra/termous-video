//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package h264

import (
	"termous/video/frame"
	"termous/video/internal/native"
	"testing"
)

func TestColorMatrixDecodedAndVUI(t *testing.T) {
	for _, tc := range []struct {
		matrix  Matrix
		y, u, v int
	}{{Matrix601, 82, 90, 240}, {Matrix709, 63, 102, 240}} {
		c := testConfig()
		c.Matrix = tc.matrix
		e, err := New(c)
		if err != nil {
			t.Fatal(err)
		}
		src := frame.BGRA{Size: c.Size, Stride: c.Size.Width * 4, Pixels: make([]byte, c.Size.Width*c.Size.Height*4)}
		for i := 0; i < len(src.Pixels); i += 4 {
			src.Pixels[i+2] = 255
			src.Pixels[i+3] = 255
		}
		out, err := e.EncodeBGRA(src, Options{Keyframe: true})
		e.Close()
		if err != nil {
			t.Fatal(err)
		}
		sample, err := native.TestDecode(out.Data)
		if err != nil {
			t.Fatal(err)
		}
		for i, want := range []int{tc.y, tc.u, tc.v} {
			// OpenH264 为有损编码，与既有平面测试保持相同的量化容差。
			if got := sample.YUV[i]; got < want-4 || got > want+4 {
				t.Fatalf("matrix=%d decoded=%v", tc.matrix, sample.YUV)
			}
		}
		primaries, transfer, matrix, full := readVUI(t, out.Data)
		wantMatrix := uint64(6)
		if tc.matrix == Matrix709 {
			wantMatrix = 1
		}
		if primaries != 1 || transfer != 13 || matrix != wantMatrix || full {
			t.Fatalf("VUI %d/%d/%d full=%v", primaries, transfer, matrix, full)
		}
	}
}

// 只解析本库输出的 Baseline SPS，避免编码成功却带有错误色彩描述。
type spsBits struct {
	t    *testing.T
	data []byte
	bit  int
}

func (r *spsBits) read(n int) uint64 {
	r.t.Helper()
	var value uint64
	for range n {
		if r.bit >= len(r.data)*8 {
			r.t.Fatal("截断的 SPS")
		}
		value = value<<1 | uint64((r.data[r.bit/8]>>(7-r.bit%8))&1)
		r.bit++
	}
	return value
}
func (r *spsBits) ue() uint64 {
	zeros := 0
	for r.read(1) == 0 {
		zeros++
		if zeros > 31 {
			r.t.Fatal("非法 Exp-Golomb")
		}
	}
	return (uint64(1) << zeros) - 1 + r.read(zeros)
}
func readVUI(t *testing.T, data []byte) (uint64, uint64, uint64, bool) {
	t.Helper()
	var sps []byte
	for i := 0; i+5 < len(data); i++ {
		if data[i] == 0 && data[i+1] == 0 && data[i+2] == 0 && data[i+3] == 1 && data[i+4]&31 == 7 {
			sps = data[i+5:]
			break
		}
	}
	if sps == nil {
		t.Fatal("缺少 SPS")
	}
	var rbsp []byte
	for i, b := range sps {
		if i >= 2 && b == 3 && sps[i-1] == 0 && sps[i-2] == 0 {
			continue
		}
		rbsp = append(rbsp, b)
	}
	r := spsBits{t: t, data: rbsp}
	if r.read(8) != 66 {
		t.Fatal("需要 Baseline SPS")
	}
	r.read(16)
	r.ue()
	r.ue()
	switch r.ue() {
	case 0:
		r.ue()
	case 1:
		r.read(1)
		r.ue()
		r.ue()
		n := r.ue()
		for range n {
			r.ue()
		}
	}
	r.ue()
	r.read(1)
	r.ue()
	r.ue()
	if r.read(1) == 0 {
		r.read(1)
	}
	r.read(1)
	if r.read(1) != 0 {
		for range 4 {
			r.ue()
		}
	}
	if r.read(1) == 0 {
		t.Fatal("缺少 VUI")
	}
	if r.read(1) != 0 {
		if r.read(8) == 255 {
			r.read(32)
		}
	}
	if r.read(1) != 0 {
		r.read(1)
	}
	if r.read(1) == 0 {
		t.Fatal("缺少 video_signal_type")
	}
	r.read(3)
	full := r.read(1) != 0
	if r.read(1) == 0 {
		t.Fatal("缺少 colour_description")
	}
	return r.read(8), r.read(8), r.read(8), full
}
