//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package color_test

import (
	"bytes"
	"encoding/binary"
	"errors"
	"image"
	"image/png"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"termous/video/color"
	"termous/video/frame"
	"termous/video/h264"
	"termous/video/internal/native"
	"testing"
)

func TestNormalizedDesktopPNGAndH264(t *testing.T) {
	p, err := color.New(color.Options{})
	if err != nil {
		if runtime.GOOS != "windows" && os.Getenv("TERMOUS_VIDEO_REQUIRE_COLOR") != "1" && errors.Is(err, color.ErrUnavailable) {
			t.Skipf("GPU unavailable: %v", err)
		}
		t.Fatal(err)
	}
	defer p.Close()
	for _, tc := range []struct {
		name string
		rgb  [3]uint16
	}{
		{"white", [3]uint16{0x4100, 0x4100, 0x4100}},
		{"gray", [3]uint16{0x3900, 0x3900, 0x3900}},
		{"red", [3]uint16{0x3900, 0, 0}},
		{"wide-green", [3]uint16{0xbde0, 0x41aa, 0xb406}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			cfg := h264.Config{Size: frame.Size{Width: 64, Height: 64},
				Rate: h264.RateControl{Bitrate: 1_000_000, FPS: 30}, Level: h264.Level31, Matrix: h264.Matrix709}
			src := frame.RGBA16F{Size: cfg.Size, Stride: cfg.Size.Width * 8, SDRWhiteNits: 200, Pixels: make([]byte, cfg.Size.Width*cfg.Size.Height*8)}
			for i := 0; i < len(src.Pixels); i += 8 {
				for c, v := range tc.rgb {
					binary.LittleEndian.PutUint16(src.Pixels[i+c*2:], v)
				}
				binary.LittleEndian.PutUint16(src.Pixels[i+6:], 0x3c00)
			}
			dst := frame.BGRA{Size: cfg.Size, Stride: cfg.Size.Width * 4, Pixels: make([]byte, cfg.Size.Width*cfg.Size.Height*4)}
			if err = p.Process(src, dst); err != nil {
				t.Fatal(err)
			}
			img := image.NewNRGBA(image.Rect(0, 0, cfg.Size.Width, cfg.Size.Height))
			for i := 0; i < len(dst.Pixels); i += 4 {
				img.Pix[i], img.Pix[i+1], img.Pix[i+2], img.Pix[i+3] = dst.Pixels[i+2], dst.Pixels[i+1], dst.Pixels[i], 255
			}
			var lossless bytes.Buffer
			if err = png.Encode(&lossless, img); err != nil {
				t.Fatal(err)
			}
			roundtrip, err := png.Decode(bytes.NewReader(lossless.Bytes()))
			if err != nil {
				t.Fatal(err)
			}
			r, g, b, _ := roundtrip.At(0, cfg.Size.Height-1).RGBA()
			if r>>8 != uint32(dst.Pixels[2]) || g>>8 != uint32(dst.Pixels[1]) || b>>8 != uint32(dst.Pixels[0]) {
				t.Fatal("lossless channel mismatch")
			}
			e, err := h264.New(cfg)
			if err != nil {
				t.Fatal(err)
			}
			defer e.Close()
			out, err := e.EncodeBGRA(dst, h264.Options{Keyframe: true})
			if err != nil {
				t.Fatal(err)
			}
			sample, err := native.TestDecode(out.Data)
			if err != nil {
				t.Fatal(err)
			}
			// 独立 BT.709 有限范围公式，不使用生产 BGRA→I420 转换生成期望值。
			red, green, blue := float64(r>>8)/255, float64(g>>8)/255, float64(b>>8)/255
			luma := .2126*red + .7152*green + .0722*blue
			want := []float64{16 + 219*luma, 128 + 224*(blue-luma)/1.8556, 128 + 224*(red-luma)/1.5748}
			for i, v := range want {
				if math.Abs(float64(sample.YUV[i])-v) > 4 {
					t.Fatalf("decoded %v want %v", sample.YUV, want)
				}
			}
			// VUI 由编码器自身的 Matrix709 回归检查；联调测试留在色彩层，避免编码包引入 GPU 依赖。
			if folder := os.Getenv("TERMOUS_HDR_FIXTURE_OUTPUT"); folder != "" {
				if err = os.MkdirAll(folder, 0755); err != nil {
					t.Fatal(err)
				}
				if err = os.WriteFile(filepath.Join(folder, tc.name+".png"), lossless.Bytes(), 0644); err != nil {
					t.Fatal(err)
				}
				if err = os.WriteFile(filepath.Join(folder, tc.name+".h264"), out.Data, 0644); err != nil {
					t.Fatal(err)
				}
			}
		})
	}
}
