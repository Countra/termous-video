//go:build cgo && !android && !ios && darwin && arm64

package colornative

/*
#cgo CFLAGS: -std=c11 -mmacosx-version-min=13.0 -DPL_STATIC -I${SRCDIR}/../../sdk/darwin/arm64/placebo/include
#cgo LDFLAGS: ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libplacebo.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libMoltenVK.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libMoltenVK_ShaderConverter.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libMoltenVK_Common.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libspirv-cross-msl.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libspirv-cross-reflect.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libspirv-cross-glsl.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libspirv-cross-core.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libSPIRV.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libglslang.a ${SRCDIR}/../../sdk/darwin/arm64/placebo/lib/libglslang-default-resource-limits.a -mmacosx-version-min=13.0 -lc++ -lobjc -ObjC -framework Foundation -framework Metal -framework AppKit -framework IOKit -framework IOSurface -framework QuartzCore -framework CoreGraphics
*/
import "C"
