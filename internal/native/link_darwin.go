//go:build cgo && darwin && arm64 && !ios

package native

/*
#cgo CFLAGS: -mmacosx-version-min=13.0
#cgo CXXFLAGS: -std=c++17 -mmacosx-version-min=13.0 -I${SRCDIR}/../../sdk/darwin/arm64/include
#cgo LDFLAGS: -L${SRCDIR}/../../sdk/darwin/arm64/lib -ltermous_video_openh264 -ltermous_video_yuv -mmacosx-version-min=13.0 -lc++
*/
import "C"
