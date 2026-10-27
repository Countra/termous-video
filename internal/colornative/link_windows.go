//go:build cgo && !android && !ios && windows && amd64

package colornative

/*
#cgo CFLAGS: -std=c11 -DPL_STATIC -I${SRCDIR}/../../sdk/windows/amd64/placebo/include
#cgo LDFLAGS: ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libplacebo.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libspirv-cross-c.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libspirv-cross-hlsl.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libspirv-cross-glsl.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libspirv-cross-core.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libSPIRV.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libglslang.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libglslang-default-resource-limits.a ${SRCDIR}/../../sdk/windows/amd64/placebo/lib/libplacebo_ucrt_math.a -static -lstdc++ -lwinpthread -lversion -lshlwapi -lole32 -luuid
*/
import "C"
