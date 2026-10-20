# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""QR codes as SVG, drawn on the server (python `qrcode`, already used by
api/qr_code.py): sharp at any size — projector, A4 print — and downloadable.
Used by the TIQN Quiz and Employee Self Update Info Setting forms."""

import io

import frappe


def make_qr_svg(text):
	import qrcode
	import qrcode.image.svg

	img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, box_size=20, border=2)
	buf = io.BytesIO()
	img.save(buf)
	return buf.getvalue().decode()


@frappe.whitelist()
def get_qr_svg(text):
	"""Any logged-in Desk user: a QR of a link is not sensitive."""
	if not text:
		frappe.throw(frappe._("Nothing to encode"))
	return make_qr_svg(text)
