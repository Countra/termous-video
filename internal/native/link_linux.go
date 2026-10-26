//go:build cgo && linux && amd64 && !android

package native

/*
#cgo CXXFLAGS: -std=c++17 -I${SRCDIR}/../../sdk/linux/amd64/include
#cgo LDFLAGS: -L${SRCDIR}/../../sdk/linux/amd64/lib -ltermous_video_openh264 -ltermous_video_yuv -static-libgcc -Wl,-Bstatic -lstdc++ -Wl,-Bdynamic -lm -pthread
*/
import "C"
