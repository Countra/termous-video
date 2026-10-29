//go:build video_native_fixture && cgo && !android && !ios && ((windows && amd64) || (linux && amd64) || (darwin && arm64))

package colornative

/*
int tv_color_test_dispatch(void);
*/
import "C"

func testDispatch() int { return int(C.tv_color_test_dispatch()) }
