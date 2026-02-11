import os
import base64
from io import BytesIO

import frappe

import qrcode
from PIL import Image

LOGO_PATH = os.path.join(
	frappe.get_app_path("customize_erpnext"), "public", "images", "logo_500.jpg"
)


@frappe.whitelist()
def generate_qr(content, size=500, use_logo=1):
	size = max(100, min(2000, int(size or 500)))
	use_logo = int(use_logo)

	error_correction = (
		qrcode.constants.ERROR_CORRECT_H if use_logo else qrcode.constants.ERROR_CORRECT_L
	)
	qr = qrcode.QRCode(
		version=None,
		error_correction=error_correction,
		box_size=10,
		border=2,
	)
	qr.add_data(content)
	qr.make(fit=True)

	qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGBA")
	qr_img = qr_img.resize((size, size), Image.LANCZOS)

	if use_logo and os.path.exists(LOGO_PATH):
		logo = Image.open(LOGO_PATH).convert("RGBA")
		logo_max = size // 4
		logo.thumbnail((logo_max, logo_max), Image.LANCZOS)

		lw, lh = logo.size
		pad = 6
		bg = Image.new("RGBA", (lw + pad * 2, lh + pad * 2), "white")
		bg.paste(logo, (pad, pad), logo)

		pos = ((size - bg.width) // 2, (size - bg.height) // 2)
		qr_img.paste(bg, pos, bg)

	buf = BytesIO()
	qr_img.convert("RGB").save(buf, format="PNG")

	return base64.b64encode(buf.getvalue()).decode()
