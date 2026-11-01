package color_test

import (
	"fmt"
	"slices"
	"testing"
	"time"

	"termous/video/color"
	"termous/video/frame"
	"termous/video/h264"
	"termous/video/internal/testpattern"
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
			scratch := frame.BGRA{Size: size, Stride: mode.w * 4, Pixels: make([]byte, mode.w*mode.h*4)}
			dst := frame.BGRA{Size: size, Stride: mode.w * 4, Pixels: make([]byte, mode.w*mode.h*4)}
			rate := h264.RateControl{Bitrate: 100_000_000, FPS: mode.fps}
			level, err := h264.MinimumLevel(size, rate)
			if err != nil {
				b.Fatal(err)
			}
			e, err := h264.New(h264.Config{Size: size, Rate: rate, Level: level, Matrix: h264.Matrix709})
			if err != nil {
				b.Fatal(err)
			}
			defer e.Close()
			b.Logf("色彩后端=%s，编码器=%s，实际线程=%d", p.Backend(), e.Info().Implementation, e.Info().Threads)
			// 预热转换器、色彩 LUT 和编码器，统计只包含稳态同步成本。
			for i := 0; i < 120; i++ {
				testpattern.HDR(src, scratch, i)
				if err = p.Process(src, dst); err != nil {
					b.Fatal(err)
				}
				if _, err = e.EncodeBGRA(dst, h264.Options{TimestampMS: int64(i * 1000 / mode.fps)}); err != nil {
					b.Fatal(err)
				}
			}
			samples := make([]float64, b.N)
			colorSamples, encodeSamples := make([]float64, b.N), make([]float64, b.N)
			b.ReportAllocs()
			b.ResetTimer()
			outputs := 0
			var colorTime, encodeTime, totalTime time.Duration
			for i := 0; i < b.N; i++ {
				testpattern.HDR(src, scratch, i+120)
				start := time.Now()
				if err = p.Process(src, dst); err != nil {
					b.Fatal(err)
				}
				encodedAt := time.Now()
				colorTime += encodedAt.Sub(start)
				colorSamples[i] = float64(encodedAt.Sub(start).Nanoseconds())
				out, err := e.EncodeBGRA(dst, h264.Options{TimestampMS: int64((i + 120) * 1000 / mode.fps)})
				if err != nil {
					b.Fatal(err)
				}
				if !out.Skipped {
					outputs++
				}
				duration := time.Since(encodedAt)
				encodeTime += duration
				encodeSamples[i] = float64(duration.Nanoseconds())
				total := time.Since(start)
				totalTime += total
				samples[i] = float64(total.Nanoseconds())
			}
			b.StopTimer()
			// 生成素材参与轮次时长，报告的处理吞吐与耗时不包含造图成本。
			b.ReportMetric(float64(totalTime.Nanoseconds())/float64(b.N), "ns/op")
			b.ReportMetric(float64(outputs)/totalTime.Seconds(), "output/s")
			slices.Sort(samples)
			slices.Sort(colorSamples)
			slices.Sort(encodeSamples)
			if len(samples) > 0 {
				b.ReportMetric(float64(colorTime.Nanoseconds())/float64(b.N)/1e6, "color-ms")
				b.ReportMetric(float64(encodeTime.Nanoseconds())/float64(b.N)/1e6, "encode-ms")
				b.ReportMetric(samples[(len(samples)*95-1)/100]/1e6, "p95-ms")
				b.ReportMetric(colorSamples[(len(samples)*95-1)/100]/1e6, "color-p95-ms")
				b.ReportMetric(encodeSamples[(len(samples)*95-1)/100]/1e6, "encode-p95-ms")
			}
		})
	}
}
