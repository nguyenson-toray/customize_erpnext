"""/qr-login-card?user=<user> — QR Login card preview + PNG download (System Manager).

Opened from the "QR Login" buttons on the User form. See customize_erpnext/api/qr_login.py.
"""

import frappe

from customize_erpnext.api.qr_login import get_card_context


def get_context(context):
	context.no_cache = 1
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=" + frappe.utils.quote(
			frappe.request.full_path if frappe.request else "/app"
		)
		raise frappe.Redirect

	user = frappe.form_dict.get("user")
	if not user:
		frappe.throw(frappe._("Missing user"))
	context.card = get_card_context(user)  # checks role + enabled
	return context
