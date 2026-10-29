//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package colornative

import (
	"os"
	"runtime"
	"testing"
)

func TestSingleDispatchAndDynamicWhite(t *testing.T) {
	if failure := testDispatch(); failure != 0 {
		if failure == 1 && runtime.GOOS != "windows" && os.Getenv("TERMOUS_VIDEO_REQUIRE_COLOR") != "1" {
			t.Skip("GPU unavailable")
		}
		t.Fatalf("dispatch count or shader reuse: %d", failure)
	}
}
