package color

import (
	"bytes"
	"encoding/binary"
	"fmt"
	"math"
	"runtime"
	"termous/video/frame"
	"testing"
)

// 参考曲线由拐点处连续、斜率为 1、峰值映射到 1 三个约束独立求解。
// 不调用生产 Shader 或 libplacebo 的 LUT 生成器。
func desktopReference(x float64) float64 {
	const knee, peak = 0.9, 10.0
	x = math.Max(0, math.Min(peak, x))
	if x > knee {
		x = knee + (x-knee)/(1+(x-knee)*(peak-1)/((1-knee)*(peak-knee)))
	}
	return srgbEncode(x) * 255
}

func srgbEncode(x float64) float64 {
	if x <= 0.0031308 {
		return x * 12.92
	}
	return 1.055*math.Pow(x, 1/2.4) - 0.055
}
func srgbDecode(x float64) float64 {
	if x <= 0.04045 {
		return x / 12.92
	}
	return math.Pow((x+0.055)/1.055, 2.4)
}

// 测试素材使用独立的二进制指数分解，允许合法负值和半精度量化误差。
func fixtureHalf(x float64) uint16 {
	sign := uint16(0)
	if x < 0 {
		sign = 0x8000
		x = -x
	}
	if x < math.Ldexp(1, -14) {
		return sign | uint16(math.RoundToEven(math.Ldexp(x, 24)))
	}
	m, e := math.Frexp(x)
	return sign | uint16((e+14)*1024+int(math.RoundToEven((m*2-1)*1024)))
}

func fixtureFrame(rgb [][3]float64, white float32) (frame.RGBA16F, frame.BGRA) {
	size := frame.Size{Width: len(rgb), Height: 2}
	src := frame.RGBA16F{Size: size, Stride: size.Width * 8, SDRWhiteNits: white, Pixels: make([]byte, size.Width*16)}
	for y := 0; y < 2; y++ {
		for x, pixel := range rgb {
			for c, value := range pixel {
				binary.LittleEndian.PutUint16(src.Pixels[y*src.Stride+x*8+c*2:], fixtureHalf(value*float64(white)/80))
			}
			binary.LittleEndian.PutUint16(src.Pixels[y*src.Stride+x*8+6:], 0x3c00)
		}
	}
	return src, frame.BGRA{Size: size, Stride: size.Width * 4, Pixels: make([]byte, size.Width*8)}
}

func TestDesktopReferenceProperties(t *testing.T) {
	previous := 0.0
	for i := 0; i <= 10000; i++ {
		value := desktopReference(float64(i) / 1000)
		if math.IsNaN(value) || value < previous || value > 255.000001 {
			t.Fatalf("invalid reference at %d: %f", i, value)
		}
		previous = value
	}
	if math.Abs(desktopReference(.9-1e-8)-desktopReference(.9+1e-8)) > 1e-5 {
		t.Fatal("discontinuous knee")
	}
}

func TestDesktopWhiteAndGamut(t *testing.T) {
	if !QueryCapabilities().Compiled {
		t.Skip("native color unavailable")
	}
	var hardware []byte
	for _, software := range []bool{false, true} {
		if software && runtime.GOOS != "windows" {
			continue
		}
		p := newTestProcessor(t, software)
		grays := []int{0, 64, 128, 192, 224, 240, 248, 255}
		var rgb [][3]float64
		for _, g := range grays {
			v := srgbDecode(float64(g) / 255)
			rgb = append(rgb, [3]float64{v, v, v})
		}
		for _, v := range []float64{2, 4, 10} {
			rgb = append(rgb, [3]float64{v, v, v})
		}
		// 色域内原色与非对称中间色检查矩阵方向和通道顺序。
		colors := [][3]float64{{.25, 0, 0}, {0, .25, 0}, {0, 0, .25}, {.1, .3, .5}}
		rgb = append(rgb, colors...)
		// D65 P3 与 BT.2020 原色转换到线性 709 后包含负分量，不能在入口裁剪。
		wide := [][3]float64{{1.22494, -.04206, -.01964}, {-.22494, 1.04206, -.07864}, {1.66049, -.12455, -.01815}, {-.58764, 1.13290, -.10058}}
		rgb = append(rgb, wide...)
		var baseline []byte
		for _, white := range []float32{80, 120, 200, 300, 400, 80} {
			t.Run(fmt.Sprintf("software=%v/white=%g", software, white), func(t *testing.T) {
				src, dst := fixtureFrame(rgb, white)
				if err := p.Process(src, dst); err != nil {
					t.Fatal(err)
				}
				for i := 0; i < len(grays)+3; i++ {
					want := desktopReference(rgb[i][0])
					for c := 0; c < 3; c++ {
						if math.Abs(float64(dst.Pixels[i*4+c])-want) > 2 {
							t.Errorf("gray %d channel %d: got %d want %.2f", i, c, dst.Pixels[i*4+c], want)
						}
					}
				}
				for i := 1; i < len(grays); i++ {
					if dst.Pixels[i*4] <= dst.Pixels[(i-1)*4] {
						t.Fatalf("gray levels collapsed at %d", grays[i])
					}
				}
				for i, pixel := range colors {
					for c, v := range pixel {
						got := dst.Pixels[(len(grays)+3+i)*4+2-c]
						// 原色边界的 LUT 插值按线性光能量约束；中间色仍按两个量化级验收。
						bad := math.Abs(float64(got)-srgbEncode(v)*255) > 2
						if v == 0 {
							bad = srgbDecode(float64(got)/255) > 0.004
						}
						if bad {
							t.Errorf("color %d/%d: got %d", i, c, got)
						}
					}
				}
				if baseline == nil {
					baseline = bytes.Clone(dst.Pixels)
				} else {
					for i, v := range dst.Pixels {
						if math.Abs(float64(v)-float64(baseline[i])) > 2 {
							t.Fatalf("white dependence byte %d: %d/%d", i, v, baseline[i])
						}
					}
				}
				// 显示参考峰值不参与桌面曝光；其他像素变化也不得改变固定 UI 色块。
				src.PeakNits = 4000
				binary.LittleEndian.PutUint16(src.Pixels[len(src.Pixels)-8:], fixtureHalf(100))
				if err := p.Process(src, dst); err != nil {
					t.Fatal(err)
				}
				if !bytes.Equal(dst.Pixels[:dst.Stride], baseline[:dst.Stride]) && white == 80 {
					t.Fatal("content or display peak changed exposure")
				}
			})
		}
		if !software {
			hardware = baseline
		} else {
			for i, v := range baseline {
				if math.Abs(float64(v)-float64(hardware[i])) > 2 {
					t.Fatalf("hardware/WARP byte %d: %d/%d", i, v, hardware[i])
				}
			}
		}
	}
}

func TestDesktopInvalidAndExtremeSamples(t *testing.T) {
	if !QueryCapabilities().Compiled {
		t.Skip("native color unavailable")
	}
	p := newTestProcessor(t, false)
	src, dst := fixtureFrame([][3]float64{{.2, .3, .4}}, 80)
	for _, v := range []uint16{0x7c00, 0xfc00, 0x7e00, 0xfe00} {
		binary.LittleEndian.PutUint16(src.Pixels, v)
		if p.Process(src, dst) != frame.ErrInvalid {
			t.Fatalf("accepted special half %x", v)
		}
	}
	for _, v := range []uint16{0x7bff, 0xfbff, 0x8000} {
		binary.LittleEndian.PutUint16(src.Pixels, v)
		if err := p.Process(src, dst); err != nil {
			t.Fatalf("finite half %x: %v", v, err)
		}
	}
}
