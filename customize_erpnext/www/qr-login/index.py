"""/qr-login — scan a personal QR card to sign in on a shared device.

Public page (guest). The device bookmark chooses where the user lands:
    /qr-login?next=/app/overtime-registration/new
See customize_erpnext/api/qr_login.py.
"""

import frappe

from customize_erpnext.api.qr_login import safe_next


def get_context(context):
	context.no_cache = 1
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.next_url = safe_next(frappe.form_dict.get("next"))
	return context
