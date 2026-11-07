//go:build video_native_fixture

package h264

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"testing"

	"termous/video/frame"
)

// 稀疏输入仍须同步返回一帧；主动修复只使用现有编码器的完整 IDR。
func TestSparseReferenceRefreshPixels(t *testing.T) {
	dir, ffmpeg := os.Getenv("TERMOUS_VIDEO_REFERENCE_OUTPUT"), os.Getenv("TERMOUS_FFMPEG")
	if dir == "" || ffmpeg == "" {
		t.Skip("未指定原分辨率编码验证目录和 FFmpeg")
	}
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	for _, stressed := range []bool{false, true} {
		name := "fixed"
		if stressed {
			name = "pressure-recovery"
		}
		t.Run(name, func(t *testing.T) {
			const width, height, count = 2560, 1440, 96
			e, err := New(Config{Size: frame.Size{Width: width, Height: height}, Rate: RateControl{Bitrate: 24_000_000, FPS: 60}, Level: Level51, Matrix: Matrix709})
			if err != nil {
				t.Fatal(err)
			}
			defer e.Close()
			var encoded bytes.Buffer
			qps := make([]uint8, 0, count)
			var timestamp int64
			for i := 0; i < count; i++ {
				rgb := referenceRGB(i, width, height)
				bgra := make([]byte, width*height*4)
				for p := 0; p < width*height; p++ {
					bgra[p*4], bgra[p*4+1], bgra[p*4+2], bgra[p*4+3] = rgb[p*3+2], rgb[p*3+1], rgb[p*3], 255
				}
				var rate *RateControl
				if stressed && i == 40 {
					rate = &RateControl{Bitrate: 256_000, FPS: 60}
				}
				if stressed && i == 60 {
					rate = &RateControl{Bitrate: 24_000_000, FPS: 60}
				}
				if i >= 40 && i < 80 {
					timestamp += 1000
				} else {
					timestamp += 17
				}
				out, err := e.EncodeBGRA(frame.BGRA{Size: frame.Size{Width: width, Height: height}, Stride: width * 4, Pixels: bgra}, Options{TimestampMS: timestamp, Keyframe: i == 0 || i == 70, Rate: rate})
				if err != nil || out.Skipped || out.TimestampMS != timestamp {
					t.Fatalf("第 %d 帧未同步交付：%v", i, err)
				}
				if i == 70 && (!out.Keyframe || !referenceIDR(out.Data)) {
					t.Fatal("同编码器修复缺少 SPS/PPS/IDR")
				}
				encoded.Write(out.Data)
				qps = append(qps, out.QPPlusOne)
			}
			if err = os.WriteFile(filepath.Join(dir, name+".h264"), encoded.Bytes(), 0600); err != nil {
				t.Fatal(err)
			}
			cmd := exec.CommandContext(t.Context(), ffmpeg, "-v", "error", "-err_detect", "explode", "-f", "h264", "-i", "pipe:0", "-fps_mode", "passthrough", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1")
			cmd.Stdin = bytes.NewReader(encoded.Bytes())
			var stderr bytes.Buffer
			cmd.Stderr = &stderr
			decoded, err := cmd.StdoutPipe()
			if err != nil {
				t.Fatal(err)
			}
			if err = cmd.Start(); err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() {
				if cmd.ProcessState == nil {
					_ = cmd.Process.Kill()
					_ = cmd.Wait()
				}
			})
			type measurement struct {
				Frame, QP   int
				Mean, Worst float64
			}
			var report []measurement
			pixels := make([]byte, width*height*3)
			failures := 0
			for i := 0; i < count; i++ {
				if _, err = io.ReadFull(decoded, pixels); err != nil {
					t.Fatalf("解码帧 %d: %v %s", i, err, stderr.String())
				}
				mean, worst := referenceError(referenceRGB(i, width, height), pixels, width, height)
				report = append(report, measurement{i, int(qps[i]) - 1, mean, worst})
				// 注入压力区间保留失真值，独立考察预算恢复及修复后的严格图像门禁。
				if (!stressed || i >= 70) && (mean > 6 || worst > 18) {
					failures++
				}
			}
			var extra [1]byte
			if n, e := decoded.Read(extra[:]); n != 0 || e != io.EOF {
				t.Fatal("解码帧数不一致", n, e)
			}
			if err = cmd.Wait(); err != nil {
				t.Fatal(err, stderr.String())
			}
			data, err := json.MarshalIndent(report, "", "  ")
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(filepath.Join(dir, name+".json"), data, 0600); err != nil {
				t.Fatal(err)
			}
			if failures > 0 {
				t.Fatalf("%d 帧超过均值 6／区域 18 门禁；保留原始失败记录", failures)
			}
		})
	}
}

func referenceIDR(data []byte) bool {
	var sps, pps, idr bool
	for i := 0; i+4 < len(data); i++ {
		if data[i] == 0 && data[i+1] == 0 && data[i+2] == 1 {
			switch data[i+3] & 31 {
			case 7:
				sps = true
			case 8:
				pps = true
			case 5:
				idr = true
			}
		}
	}
	return sps && pps && idr
}

func referenceRGB(index, width, height int) []byte {
	pixels := make([]byte, width*height*3)
	step := index
	if index >= 40 && index < 80 {
		step = 40
	}
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			v := byte(12)
			if y > 80 && y < height-80 && x > 160 && x < width-256 && y%48 >= 16 && y%48 < 32 && x%32 >= 8 && x%32 < 24 {
				v = 180
			}
			if y >= 40 && y < 64 && x >= 160+step*16 && x < 224+step*16 {
				v = 224
			}
			i := (y*width + x) * 3
			pixels[i], pixels[i+1], pixels[i+2] = v, v, v
		}
	}
	return pixels
}

func referenceError(raw, pixels []byte, width, height int) (float64, float64) {
	var sum, worst float64
	var samples int
	for y := 0; y < height; y++ {
		if y%8 < 2 || y%8 > 5 {
			continue
		}
		for x := 0; x < width; x += 8 {
			error, n := 0, 0
			for dx := 2; dx <= 5 && x+dx < width; dx++ {
				for c := 0; c < 3; c++ {
					i := (y*width+x+dx)*3 + c
					d := int(raw[i]) - int(pixels[i])
					if d < 0 {
						d = -d
					}
					error += d
					n++
				}
			}
			if n > 0 {
				sum += float64(error)
				samples += n
				worst = max(worst, float64(error)/float64(n))
			}
		}
	}
	return sum / float64(samples), worst
}

func TestReferencePixelsDetectStripesWithoutRejectingBlack(t *testing.T) {
	const width, height = 2560, 1440
	raw := referenceRGB(40, width, height)
	mean, worst := referenceError(raw, raw, width, height)
	if mean != 0 || worst != 0 {
		t.Fatal("暗背景被误判")
	}
	damaged := append([]byte(nil), raw...)
	for y := 402; y < 406; y++ {
		for x := 128; x < 640; x++ {
			for c := 0; c < 3; c++ {
				damaged[(y*width+x)*3+c] = 96
			}
		}
	}
	_, worst = referenceError(raw, damaged, width, height)
	if worst <= 18 {
		t.Fatal("已知横条负样本未被检出", worst)
	}
}
