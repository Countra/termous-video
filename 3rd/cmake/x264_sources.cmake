# 编译单元来自固定提交的 Makefile；只构建 8 位编码库，不执行上游脚本。
set(X264_COMMON
  common/osdep.c common/base.c common/cpu.c common/tables.c encoder/api.c)
set(X264_8BIT
  common/mc.c common/predict.c common/pixel.c common/macroblock.c
  common/frame.c common/dct.c common/cabac.c common/common.c common/rectangle.c
  common/set.c common/quant.c common/deblock.c common/vlc.c common/mvpred.c
  common/bitstream.c encoder/analyse.c encoder/me.c encoder/ratecontrol.c
  encoder/set.c encoder/macroblock.c encoder/cabac.c encoder/cavlc.c
  encoder/encoder.c encoder/lookahead.c common/threadpool.c)
set(X264_X86_C common/x86/mc-c.c common/x86/predict-c.c)
set(X264_X86_ASM
  common/x86/dct-64.asm common/x86/trellis-64.asm common/x86/bitstream-a.asm
  common/x86/const-a.asm common/x86/cabac-a.asm common/x86/dct-a.asm
  common/x86/deblock-a.asm common/x86/mc-a.asm common/x86/mc-a2.asm
  common/x86/pixel-a.asm common/x86/predict-a.asm common/x86/quant-a.asm
  common/x86/sad-a.asm)
set(X264_ARM_C
  common/aarch64/asm-offsets.c common/aarch64/mc-c.c common/aarch64/predict-c.c)
set(X264_ARM_ASM
  common/aarch64/bitstream-a.S common/aarch64/cabac-a.S common/aarch64/dct-a.S
  common/aarch64/deblock-a.S common/aarch64/mc-a.S common/aarch64/pixel-a.S
  common/aarch64/predict-a.S common/aarch64/quant-a.S)
