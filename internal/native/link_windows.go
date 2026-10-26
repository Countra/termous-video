//go:build cgo && windows && amd64

package native

/*
#cgo CXXFLAGS: -std=c++17 -I${SRCDIR}/../../sdk/windows/amd64/include
#cgo LDFLAGS: -L${SRCDIR}/../../sdk/windows/amd64/lib -ltermous_video_openh264 -ltermous_video_yuv -static -static-libgcc -static-libstdc++ -lstdc++ -lwinpthread
*/
import "C"
