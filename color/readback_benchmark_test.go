package color_test

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"slices"
	"termous/video/color"
	"termous/video/frame"
	"termous/video/internal/testpattern"
	"testing"
	"time"
)

type readbackSample struct {
	AgeMS  float64       `json:"age_ms"`
	Stages color.Timings `json:"stages"`
}
type readbackRun struct {
	Width, Height, Hz, Round    int
	Async, Measure              bool
	Device                      string
	Frames, Missed              int
	FPS, P95MS, MeanMS          float64
	AllocatedBytes, Allocations uint64
	Resources                   color.Resources
	Samples                     []readbackSample
}

// 显式启用的隔离对照，不启动桌面采集或编码，不代替真实 WGC 验收。
func TestReadbackPerformanceMatrix(t *testing.T) {
	path := os.Getenv("TERMOUS_HDR_READBACK_MATRIX")
	if path == "" {
		t.Skip("仅显式运行隔离性能矩阵")
	}
	var runs []readbackRun
	focus := os.Getenv("TERMOUS_HDR_READBACK_FOCUS") == "1"
	frequencies := []int{20, 30, 60, 0}
	if focus {
		frequencies = []int{60}
	}
	for round := 0; round < 3; round++ {
		for _, size := range []frame.Size{{Width: 1920, Height: 1080}, {Width: 2560, Height: 1440}} {
			for _, hz := range frequencies {
				order := []bool{false, true}
				if round%2 != 0 {
					slices.Reverse(order)
				}
				for _, async := range order {
					run := measureReadback(t, size, hz, async, false)
					run.Round = round + 1
					runs = append(runs, run)
					t.Logf("%dx%d hz=%d async=%t round=%d fps=%.2f age_p95=%.3f missed=%d", size.Width, size.Height, hz, async, round+1, run.FPS, run.P95MS, run.Missed)
				}
			}
		}
	}
	// GPU 查询开关的对照与正式关闭诊断的三轮数据分开。
	for _, hz := range []int{20, 30, 60} {
		if focus {
			break
		}
		runs = append(runs, measureReadback(t, frame.Size{Width: 2560, Height: 1440}, hz, true, true))
	}
	data, err := json.MarshalIndent(runs, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
}

func measureReadback(t *testing.T, size frame.Size, hz int, async, measure bool) readbackRun {
	t.Helper()
	p, err := color.New(color.Options{MeasureStages: measure})
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()
	src := frame.RGBA16F{Size: size, Stride: size.Width * 8, Pixels: make([]byte, size.Width*size.Height*8), SDRWhiteNits: 200}
	scratch := frame.BGRA{Size: size, Stride: size.Width * 4, Pixels: make([]byte, size.Width*size.Height*4)}
	testpattern.HDR(src, scratch, 173)
	outputs := []frame.BGRA{scratch, {Size: size, Stride: size.Width * 4, Pixels: make([]byte, size.Width*size.Height*4)}}
	run := readbackRun{Width: size.Width, Height: size.Height, Hz: hz, Async: async, Measure: measure, Device: p.Device()}
	if async {
		run.Resources, err = p.AsyncResources(size)
		if err != nil {
			t.Fatal(err)
		}
		if err = p.PrepareAsync(size); err != nil {
			t.Fatal(err)
		}
	}
	// 相同模式预热后重新建立测量窗口；素材不在计时内生成。
	warmup, count := 30, 120
	if os.Getenv("TERMOUS_HDR_READBACK_FOCUS") == "1" {
		warmup, count = 120, 600
	}
	for i := 0; i < warmup; i++ {
		start := time.Now()
		if async {
			ticket, e := p.Submit(src)
			if e != nil {
				t.Fatal(e)
			}
			for {
				ready, e := p.Ready(ticket)
				if e != nil {
					t.Fatal(e)
				}
				if ready {
					if _, e = p.Collect(ticket, outputs[0]); e != nil {
						t.Fatal(e)
					}
					break
				}
				time.Sleep(time.Millisecond)
			}
		} else {
			if err = p.Process(src, outputs[0]); err != nil {
				t.Fatal(err)
			}
		}
		if hz > 0 {
			time.Sleep(time.Second/time.Duration(hz) - time.Since(start))
		}
	}
	type inflight struct {
		ticket color.Ticket
		start  time.Time
		slot   int
	}
	var tasks []inflight
	var busy [2]bool
	run.Samples = make([]readbackSample, 0, count)
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	start := time.Now()
	next := start
	period := time.Duration(0)
	if hz > 0 {
		period = time.Second / time.Duration(hz)
	}
	submitted := 0
	var pollDue time.Time
	finish := func(at time.Time, stages color.Timings) {
		run.Samples = append(run.Samples, readbackSample{AgeMS: float64(time.Since(at)) / 1e6, Stages: stages})
	}
	for len(run.Samples) < count {
		if time.Since(start) > 30*time.Second {
			t.Fatal("性能对照超时")
		}
		for i := 0; i < len(tasks); {
			job := tasks[i]
			ready, e := p.Ready(job.ticket)
			if e != nil {
				t.Fatal(e)
			}
			if !ready {
				i++
				continue
			}
			stages, e := p.Collect(job.ticket, outputs[job.slot])
			if e != nil {
				t.Fatal(e)
			}
			finish(job.start, stages)
			busy[job.slot] = false
			tasks = append(tasks[:i], tasks[i+1:]...)
		}
		if submitted < count && !time.Now().Before(next) && (!async || len(tasks) < 2) {
			at := time.Now()
			if period > 0 {
				// 记录错过的来源时隙；不靠补发旧帧制造满帧率。
				missed := int(at.Sub(next) / period)
				run.Missed += missed
				next = next.Add(time.Duration(missed+1) * period)
			}
			if async {
				slot := 0
				if busy[0] {
					slot = 1
				}
				busy[slot] = true
				ticket, e := p.Submit(src)
				if e != nil {
					t.Fatal(e)
				}
				tasks = append(tasks, inflight{ticket, at, slot})
			} else {
				if err = p.Process(src, outputs[0]); err != nil {
					t.Fatal(err)
				}
				finish(at, p.Timings())
			}
			submitted++
			continue
		}
		if len(run.Samples) == count {
			break
		}
		wait := time.Until(next)
		if len(tasks) > 0 {
			now := time.Now()
			if pollDue.IsZero() {
				pollDue = now.Add(time.Millisecond)
			}
			if !now.Before(pollDue) {
				pollDue = pollDue.Add((now.Sub(pollDue)/time.Millisecond + 1) * time.Millisecond)
			}
			pollWait := time.Until(pollDue)
			if wait <= 0 || submitted == count || len(tasks) == 2 {
				wait = pollWait
			} else {
				wait = min(wait, pollWait)
			}
		} else {
			pollDue = time.Time{}
		}
		if wait > 0 {
			time.Sleep(wait)
		}
	}
	elapsed := time.Since(start)
	runtime.ReadMemStats(&after)
	run.Frames = count
	run.FPS = float64(count) / elapsed.Seconds()
	run.AllocatedBytes = after.TotalAlloc - before.TotalAlloc
	run.Allocations = after.Mallocs - before.Mallocs
	ages := make([]float64, count)
	for i, s := range run.Samples {
		ages[i] = s.AgeMS
		run.MeanMS += s.AgeMS / float64(count)
	}
	slices.Sort(ages)
	run.P95MS = ages[(count*95-1)/100]
	if run.Device == "" {
		t.Fatal(fmt.Errorf("缺少设备诊断"))
	}
	return run
}
