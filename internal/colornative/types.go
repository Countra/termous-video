package colornative

import (
	"errors"
	"time"
)

var (
	ErrUnavailable = errors.New("video: HDR conversion backend unavailable")
	ErrFailed      = errors.New("video: HDR conversion failed")
	ErrClosed      = errors.New("video: color processor closed")
	ErrBusy        = errors.New("video: color processor busy")
)

// DownloadWait 包含同步下载的 GPU 等待和读回，不等同于 CPU 运算。
type Timings struct {
	Submit                                                time.Duration
	Validate, Upload, Dispatch, DownloadWait, DispatchGPU time.Duration
	Map, Copy, UploadGPU, DownloadGPU                     time.Duration
	GPUValid                                              bool
}

type Resources struct{ HostBytes, DeviceBytes uint64 }
