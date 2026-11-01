package h264

import (
	"fmt"
	"slices"
	"termous/video/frame"
	"termous/video/internal/testpattern"
	"testing"
	"time"
)

// 输入生成不计入编码时间，相同素材用于迁移前后的独立测试二进制。
func BenchmarkDesktopEncoding(b *testing.B) {
	if !QueryCapabilities().Supported {
		b.Skip("native SDK unavailable")
	}
	for _, size := range []frame.Size{{Width: 1920, Height: 1080}, {Width: 2560, Height: 1440}} {
		for _, fps := range []int{30, 60} {
			for _, bitrate := range []int{24_000_000, 50_000_000, 100_000_000} {
				b.Run(fmt.Sprintf("%dp/%dfps/%dMbps", size.Height, fps, bitrate/1_000_000), func(b *testing.B) {
					benchmarkDesktop(b, Config{Size: size, Rate: RateControl{Bitrate: bitrate, FPS: fps}, Level: Level51, Matrix: Matrix709})
				})
			}
		}
	}
}

func BenchmarkDesktopThreads(b *testing.B) {
	for _, threads := range []int{1, 4, 8, 16} {
		b.Run(fmt.Sprint(threads), func(b *testing.B) {
			benchmarkDesktop(b, Config{Size: frame.Size{Width: 2560, Height: 1440}, Rate: RateControl{Bitrate: 100_000_000, FPS: 60}, Level: Level51, Matrix: Matrix709, Threads: threads})
		})
	}
}

func benchmarkDesktop(b *testing.B, config Config) {
	if !QueryCapabilities().Supported {
		b.Skip("native SDK unavailable")
	}
	size, fps := config.Size, config.Rate.FPS
	e, err := New(config)
	if err != nil {
		b.Fatal(err)
	}
	defer e.Close()
	b.Logf("编码器=%s，预设=%s，实际线程=%d", e.Info().Implementation, e.Info().Preset, e.Info().Threads)
	src := frame.BGRA{Size: size, Stride: size.Width * 4, Pixels: make([]byte, size.Width*size.Height*4)}
	for i := 0; i < 120; i++ {
		testpattern.Desktop(src, i)
		if _, err = e.EncodeBGRA(src, Options{TimestampMS: int64(i * 1000 / fps)}); err != nil {
			b.Fatal(err)
		}
	}
	samples := make([]float64, b.N)
	var totalBytes, outputs, keys, maxBytes int
	var encodeTime time.Duration
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		testpattern.Desktop(src, i+120)
		start := time.Now()
		out, err := e.EncodeBGRA(src, Options{TimestampMS: int64((i + 120) * 1000 / fps)})
		duration := time.Since(start)
		encodeTime += duration
		samples[i] = float64(duration.Nanoseconds())
		if err != nil {
			b.Fatal(err)
		}
		if !out.Skipped {
			outputs++
		}
		if out.Keyframe {
			keys++
		}
		totalBytes += len(out.Data)
		maxBytes = max(maxBytes, len(out.Data))
	}
	b.StopTimer()
	slices.Sort(samples)
	// 轮次时长包含无分配造图，耗时指标只统计编码，避免逐帧暂停 Go 计时器的额外扰动。
	b.ReportMetric(float64(encodeTime.Nanoseconds())/float64(b.N), "ns/op")
	b.ReportMetric(samples[(len(samples)*95-1)/100]/1e6, "p95-ms")
	b.ReportMetric(float64(outputs)/float64(b.N), "output/input")
	b.ReportMetric(float64(totalBytes)*8*float64(fps)/float64(b.N)/1e6, "Mbps-at-fps")
	b.ReportMetric(float64(maxBytes), "max-frame-B")
	b.ReportMetric(float64(keys), "IDRs")
}
