package main

/*
int video_sdk_smoke(void);
*/
import "C"

import (
	"fmt"
	"os"
)

func main() {
	if result := C.video_sdk_smoke(); result != 0 {
		fmt.Fprintf(os.Stderr, "cgo synthetic video check failed at stage %d\n", int(result))
		os.Exit(1)
	}
}
