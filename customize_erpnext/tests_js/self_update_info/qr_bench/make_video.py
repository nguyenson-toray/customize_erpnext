"""Video camera giả (.y4m) cho perf.mjs: 1 khung QR CCCD giả lặp 30 lần (Chromium --use-file-for-fake-video-capture).
noread.y4m = mã nhỏ + mờ (không đọc được → máy quét chạy liên tục, đo độ giật); read.y4m = mã rõ (đo thời gian đọc)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))


def y4m(img, path, frames=30):
	rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
	r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
	y = (0.257 * r + 0.504 * g + 0.098 * b + 16).clip(0, 255).astype(np.uint8)
	u = (-0.148 * r - 0.291 * g + 0.439 * b + 128)[::2, ::2].clip(0, 255).astype(np.uint8)
	v = (0.439 * r - 0.368 * g - 0.071 * b + 128)[::2, ::2].clip(0, 255).astype(np.uint8)
	h, w = y.shape
	with open(path, "wb") as f:
		f.write(f"YUV4MPEG2 W{w} H{h} F30:1 Ip A1:1 C420jpeg\n".encode())
		for _ in range(frames):
			f.write(b"FRAME\n")
			f.write(y.tobytes())
			f.write(u.tobytes())
			f.write(v.tobytes())


if __name__ == "__main__":
	mat, _ = gen.qr_matrix(gen.PAYLOADS[0], "M")
	y4m(gen.frame(mat, 1.5, 1.5, True, 15), os.path.join(OUT, "noread.y4m"))
	y4m(gen.frame(mat, 3.0, 0.0, False, 0), os.path.join(OUT, "read.y4m"))
	print("ok")
