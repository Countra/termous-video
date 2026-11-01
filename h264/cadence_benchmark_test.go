package h264

import (
	"fmt"
	"slices"
	"sync"
	"testing"
	"time"

	"termous/video/frame"
	"termous/video/internal/testpattern"
)

// 固定节奏包含素材生成和调度成本；每个会话独占一个编码器，不并发调用同一实例。
func BenchmarkDesktopCadence(b *testing.B) {
	if !QueryCapabilities().Supported {
		b.Skip("native SDK unavailable")
	}
	for _, threads := range []int{4, 8, 12, 16} {
		for _, sessions := range []int{1, 2} {
			b.Run(fmt.Sprintf("%dthreads/%dsessions", threads, sessions), func(b *testing.B) {
				benchmarkCadence(b, threads, sessions)
			})
		}
	}
}

func benchmarkCadence(b *testing.B, threads, sessions int) {
	size := frame.Size{Width: 2560, Height: 1440}
	encoders := make([]*Encoder, sessions)
	frames := make([]frame.BGRA, sessions)
	samples := make([][]float64, sessions)
	for index := range encoders {
		e, err := New(Config{Size: size, Rate: RateControl{Bitrate: 100_000_000, FPS: 60}, Level: Level51, Matrix: Matrix709, Threads: threads})
		if err != nil {
			b.Fatal(err)
		}
		defer e.Close()
		encoders[index] = e
		frames[index] = frame.BGRA{Size: size, Stride: size.Width * 4, Pixels: make([]byte, size.Width*size.Height*4)}
		samples[index] = make([]float64, b.N)
		for i := 0; i < 120; i++ {
			testpattern.Desktop(frames[index], i)
			if _, err = e.EncodeBGRA(frames[index], Options{TimestampMS: int64(i * 1000 / 60)}); err != nil {
				b.Fatal(err)
			}
		}
	}
	var wg sync.WaitGroup
	errors := make(chan error, sessions)
	misses := make([]int, sessions)
	elapsed := make([]time.Duration, sessions)
	start := make(chan struct{})
	b.ReportAllocs()
	b.ResetTimer()
	for index := range encoders {
		wg.Add(1)
		go func(index int) {
			defer wg.Done()
			<-start
			begin := time.Now()
			next := begin
			for i := 0; i < b.N; i++ {
				if wait := time.Until(next); wait > 0 {
					time.Sleep(wait)
				}
				deadline := next.Add(time.Second / 60)
				testpattern.Desktop(frames[index], i+120)
				encodedAt := time.Now()
				out, err := encoders[index].EncodeBGRA(frames[index], Options{TimestampMS: int64((i + 120) * 1000 / 60)})
				if err != nil {
					errors <- err
					return
				}
				if out.Skipped {
					errors <- fmt.Errorf("session %d skipped frame", index)
					return
				}
				now := time.Now()
				samples[index][i] = float64(now.Sub(encodedAt)) / 1e6
				if now.After(deadline) {
					misses[index]++
					next = now
				} else {
					next = deadline
				}
			}
			elapsed[index] = time.Since(begin)
		}(index)
	}
	close(start)
	wg.Wait()
	b.StopTimer()
	close(errors)
	for err := range errors {
		b.Fatal(err)
	}
	var total time.Duration
	var totalMisses int
	all := make([]float64, 0, b.N*sessions)
	for index := range encoders {
		total += elapsed[index]
		totalMisses += misses[index]
		all = append(all, samples[index]...)
	}
	slices.Sort(all)
	b.ReportMetric(float64(b.N*sessions)/total.Seconds(), "fps/session")
	b.ReportMetric(float64(totalMisses)*100/float64(b.N*sessions), "deadline-miss-%")
	b.ReportMetric(all[(len(all)*95-1)/100], "encode-p95-ms")
}
