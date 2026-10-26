package frame

import "testing"

func TestPaddedFrameAndLastRow(t *testing.T) {
	f := BGRA{Size: Size{3, 2}, Stride: 16, Pixels: make([]byte, 28)}
	if f.Validate() != nil {
		t.Fatal("last row does not require trailing padding")
	}
	f.Pixels = f.Pixels[:27]
	if f.Validate() == nil {
		t.Fatal("short last row accepted")
	}
}
func TestGeometryLimits(t *testing.T) {
	for _, size := range []Size{{0, 1}, {-1, 2}, {MaxPixels, 2}, {int(^uint(0) >> 1), 2}} {
		if size.Validate() == nil {
			t.Fatalf("accepted %+v", size)
		}
	}
	f, err := NewI420(Size{3, 3})
	if err != nil || f.Validate() != nil || len(f.Y) != 9 || len(f.U) != 4 || len(f.V) != 4 {
		t.Fatalf("odd frame: %+v %v", f, err)
	}
}
