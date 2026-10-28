"""Sinh khung hình camera giả có QR kiểu CCCD để so jsQR vs ZXing-WASM (bước 0, plan cccd_qr_scanner.md).

Không dùng dữ liệu thật: họ tên / số / địa chỉ bịa, đúng định dạng QR CCCD
`<CCCD 12 số>|<CMND 9 số>|<Họ tên>|<ddmmyyyy sinh>|<Giới tính>|<Địa chỉ>|<ddmmyyyy cấp>`.

Mỗi ca → thư mục cases/<id>/:
  a0.png a1.png a2.png  = đúng pipeline hiện tại của form.js: 3 vùng cắt (cả khung / giữa 60% / giữa 35%×50%)
                          thu về rộng 900px (canvas drawImage ~ BILINEAR)
  roi.png               = pipeline đề xuất: vùng khung ngắm giữa (vuông 60% cạnh ngắn) ở độ phân giải gốc
  meta.json             = tham số + payload
"""
import io
import itertools
import json
import math
import os
import random
import sys

import numpy as np
import qrcode
from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases")
W, H = 1920, 1080
random.seed(7)
rng = np.random.default_rng(7)

PAYLOADS = [
	"051089009620|212869262|Nguyễn Văn Thử Nghiệm|04071989|Nam|Xóm 1, Thôn Phước Bình, Bình Nguyên, Bình Sơn, Quảng Ngãi|12082021",
	"051200012093|212588805|Trần Thị Mỹ Hạnh Thử|01062000|Nữ|131/9/2 đường Hùng Vương, Tổ 5, Trần Hưng Đạo, TP. Quảng Ngãi, Quảng Ngãi|30052025||||",
]
ECC = {"L": qrcode.constants.ERROR_CORRECT_L, "M": qrcode.constants.ERROR_CORRECT_M}
MODULE_PX = [1.5, 2.0, 2.5, 3.0, 4.0]   # cỡ 1 ô QR trên khung 1080p (cầm máy ~10–20cm, mã 1,5cm)
BLUR = [0.0, 0.8, 1.5]                  # sigma Gauss px — lấy nét kém / rung tay
GLARE = [False, True]                   # vệt lóa trên lớp ép nhựa
TILT = [0, 15]                          # độ nghiêng phối cảnh (độ)


def qr_matrix(payload, ecc):
	q = qrcode.QRCode(error_correction=ECC[ecc], border=4, box_size=1)
	q.add_data(payload.encode("utf-8"))
	q.make(fit=True)
	return np.array(q.get_matrix(), dtype=bool), q.version


def render_qr(mat, module_px):
	"""QR nét ở 12 px/ô rồi thu về module_px bằng LANCZOS (khử răng cưa như ảnh camera)."""
	n = mat.shape[0]
	big = Image.fromarray(np.where(mat, 25, 245).astype(np.uint8)).resize((n * 12, n * 12), Image.NEAREST)
	side = max(8, round(n * module_px))
	return big.resize((side, side), Image.LANCZOS)


def perspective(img, deg):
	if not deg:
		return img, (0, 0)
	w, h = img.size
	d = math.tan(math.radians(deg)) * w * 0.25
	# đỉnh trên co vào → giống nghiêng thẻ ra sau
	src = [(0, 0), (w, 0), (w, h), (0, h)]
	dst = [(d, d * 0.3), (w - d, d * 0.3), (w, h), (0, h)]
	coeffs = _persp_coeffs(dst, src)
	out = img.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor=233)
	return out, (0, 0)


def _persp_coeffs(pa, pb):
	m = []
	for (x, y), (u, v) in zip(pa, pb):
		m.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
		m.append([0, 0, 0, x, y, 1, -v * x, -v * y])
	a = np.array(m, dtype=float)
	b = np.array(pb, dtype=float).reshape(8)
	return np.linalg.solve(a, b).tolist()


def frame(mat, module_px, blur, glare, tilt):
	# bàn gỗ tối + thẻ sáng có hoa văn nhẹ
	bg = Image.new("L", (W, H), 70)
	qr = render_qr(mat, module_px)
	qs = qr.size[0]
	card_w, card_h = int(qs * 3.2), int(qs * 2.0)
	card = Image.new("L", (card_w, card_h), 233)
	cd = ImageDraw.Draw(card)
	for i in range(0, card_w, 9):          # hoa văn nền thẻ
		cd.line([(i, 0), (i - card_h // 2, card_h)], fill=226)
	for y in range(int(card_h * 0.15), int(card_h * 0.85), max(6, qs // 10)):  # dòng chữ giả bên trái QR
		cd.rectangle([int(card_w * 0.05), y, int(card_w * 0.55), y + max(2, qs // 40)], fill=90)
	card.paste(qr, (card_w - qs - int(qs * 0.25), (card_h - qs) // 2))
	card, _ = perspective(card, tilt)
	# QR gần giữa khung (lệch ngẫu nhiên nhỏ) — trong khung ngắm
	qx = card_w - qs - int(qs * 0.25) + qs // 2
	qy = card_h // 2
	ox = W // 2 - qx + random.randint(-int(W * 0.04), int(W * 0.04))
	oy = H // 2 - qy + random.randint(-int(H * 0.05), int(H * 0.05))
	bg.paste(card, (ox, oy))
	qcx, qcy = ox + qx, oy + qy    # tâm QR trên khung
	img = bg
	if glare:
		g = Image.new("L", (W, H), 0)
		gd = ImageDraw.Draw(g)
		cx, cy = qcx + random.randint(-qs // 4, qs // 4), qcy + random.randint(-qs // 4, qs // 4)
		gd.ellipse([cx - qs * 0.45, cy - qs * 0.2, cx + qs * 0.45, cy + qs * 0.2], fill=170)
		g = g.filter(ImageFilter.GaussianBlur(qs * 0.12))
		arr = np.array(img, dtype=float)
		alpha = np.array(g, dtype=float) / 255.0
		img = Image.fromarray(np.clip(arr * (1 - alpha) + 255 * alpha, 0, 255).astype(np.uint8))
	if blur:
		img = img.filter(ImageFilter.GaussianBlur(blur))
	arr = np.array(img, dtype=float) + rng.normal(0, 4.0, (H, W))       # nhiễu cảm biến
	img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGB")
	buf = io.BytesIO()
	img.save(buf, "JPEG", quality=80)                                    # nén như luồng camera
	return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def main(limit=None):
	os.makedirs(OUT, exist_ok=True)
	combos = list(itertools.product(range(len(PAYLOADS)), ECC, MODULE_PX, BLUR, GLARE, TILT))
	if limit:
		combos = combos[: int(limit)]
	for i, (pi, ecc, mpx, blur, glare, tilt) in enumerate(combos):
		payload = PAYLOADS[pi]
		mat, version = qr_matrix(payload, ecc)
		img = frame(mat, mpx, blur, glare, tilt)
		d = os.path.join(OUT, f"{i:04d}")
		os.makedirs(d, exist_ok=True)
		# pipeline hiện tại (form.js _qrScanLoop): 3 vùng cắt → rộng 900px
		for k, (cx, cy, cw, ch) in enumerate([(0, 0, W, H), (W * .2, H * .2, W * .6, H * .6), (W * .325, H * .25, W * .35, H * .5)]):
			crop = img.crop((int(cx), int(cy), int(cx + cw), int(cy + ch)))
			crop.resize((900, round(900 * ch / cw)), Image.BILINEAR).save(os.path.join(d, f"a{k}.png"))
		# pipeline đề xuất: khung ngắm vuông 60% cạnh ngắn, độ phân giải gốc
		s = int(H * 0.6)
		img.crop(((W - s) // 2, (H - s) // 2, (W + s) // 2, (H + s) // 2)).save(os.path.join(d, "roi.png"))
		json.dump({"payload": payload, "ecc": ecc, "version": version, "modules": int(mat.shape[0]) - 8,
			"module_px": mpx, "blur": blur, "glare": glare, "tilt": tilt}, open(os.path.join(d, "meta.json"), "w"), ensure_ascii=False)
	print("cases:", len(combos))


if __name__ == "__main__":
	main(sys.argv[1] if len(sys.argv) > 1 else None)
