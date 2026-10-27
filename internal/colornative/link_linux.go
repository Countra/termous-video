//go:build cgo && !android && !ios && linux && amd64

package colornative

/*
#cgo CFLAGS: -std=c11 -DPL_STATIC -I${SRCDIR}/../../sdk/linux/amd64/placebo/include
#cgo LDFLAGS: ${SRCDIR}/../../sdk/linux/amd64/placebo/lib/libplacebo.a ${SRCDIR}/../../sdk/linux/amd64/placebo/lib/libSPIRV.a ${SRCDIR}/../../sdk/linux/amd64/placebo/lib/libglslang.a ${SRCDIR}/../../sdk/linux/amd64/placebo/lib/libglslang-default-resource-limits.a -Wl,-Bstatic -lstdc++ -Wl,-Bdynamic -pthread -lm -ldl
*/
import "C"
