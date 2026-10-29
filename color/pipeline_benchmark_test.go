package color_test

import (
	"encoding/binary"
	"fmt"
	"slices"
	"testing"
	"time"

	"termous/video/color"
	"termous/video/frame"
	"termous/video/h264"
)

// 合成画面只比较同步转换和编码成本，不把吞吐量当成真实桌面持续帧率。
func BenchmarkHDRPipeline(b *testing.B) {
	for _, mode := range []struct{ w, h, fps int }{{1920, 1080, 30}, {2560, 1440, 60}} {
		b.Run(fmt.Sprintf("%dx%d_%dfps", mode.w, mode.h, mode.fps), func(b *testing.B) {
			p, err := color.New(color.Options{})
			if err != nil {
				b.Skipf("色彩后端不可用：%v", err)
			}
			defer p.Close()
			size := frame.Size{Width: mode.w, Height: mode.h}
			src := frame.RGBA16F{Size: size, Stride: mode.w * 8, Pixels: make([]byte, mode.w*mode.h*8), PeakNits: 1000, SDRWhiteNits: 80}
			for i := 0; i < len(src.Pixels); i += 8 {
				binary.LittleEndian.PutUint16(src.Pixels[i:], 0x3c00)
				binary.LittleEndian.PutUint16(src.Pixels[i+2:], 0x3400)
				binary.LittleEndian.PutUint16(src.Pixels[i+4:], 0x4400)
				binary.LittleEndian.PutUint16(src.Pixels[i+6:], 0x3c00)
			}
			dst := frame.BGRA{Size: size, Stride: mode.w * 4, Pixels: make([]byte, mode.w*mode.h*4)}
			rate := h264.RateControl{Bitrate: 8_000_000, FPS: mode.fps}
			level, err := h264.MinimumLevel(size, rate)
			if err != nil {
				b.Fatal(err)
			}
			e, err := h264.New(h264.Config{Size: size, Rate: rate, Level: level, Matrix: h264.Matrix709})
			if err != nil {
				b.Fatal(err)
			}
			defer e.Close()
			// 预热转换器、色彩 LUT 和编码器，统计只包含稳态同步成本。
			for i := 0; i < 30; i++ {
				if err = p.Process(src, dst); err != nil {
					b.Fatal(err)
				}
				if _, err = e.EncodeBGRA(dst, h264.Options{TimestampMS: int64(i * 1000 / mode.fps)}); err != nil {
					b.Fatal(err)
				}
			}
			samples := make([]float64, b.N)
			b.ReportAllocs()
			b.ResetTimer()
			outputs := 0
			var colorTime, encodeTime time.Duration
			for i := 0; i < b.N; i++ {
				start := time.Now()
				// 改变一个色块，保留动态输入，避免把全静止短路当作性能结果。
				for x := 0; x < 64*64; x++ {
					binary.LittleEndian.PutUint16(src.Pixels[x*8:], uint16(0x3400+(i%16)*128))
				}
				if err = p.Process(src, dst); err != nil {
					b.Fatal(err)
				}
				encodedAt := time.Now()
				colorTime += encodedAt.Sub(start)
				out, err := e.EncodeBGRA(dst, h264.Options{TimestampMS: int64((i + 30) * 1000 / mode.fps)})
				if err != nil {
					b.Fatal(err)
				}
				if !out.Skipped {
					outputs++
				}
				encodeTime += time.Since(encodedAt)
				samples[i] = float64(time.Since(start).Nanoseconds())
			}
			b.StopTimer()
			b.ReportMetric(float64(outputs)/b.Elapsed().Seconds(), "output/s")
			slices.Sort(samples)
			if len(samples) > 0 {
				b.ReportMetric(float64(colorTime.Nanoseconds())/float64(b.N)/1e6, "color-ms")
				b.ReportMetric(float64(encodeTime.Nanoseconds())/float64(b.N)/1e6, "encode-ms")
				b.ReportMetric(samples[(len(samples)*95-1)/100]/1e6, "p95-ms")
			}
		})
	}
}
