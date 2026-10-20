import os

import frappe

no_cache = 1


def get_context(context):
	# Vietnamese-only page (quiz.js hard-codes its text); server messages follow.
	context.no_cache = 1
	frappe.local.lang = "vi"
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.company = (
		frappe.defaults.get_global_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)
	here = os.path.dirname(__file__)
	context.asset_version = int(
		max(os.path.getmtime(os.path.join(here, f)) for f in ("quiz.js", "style.css"))
	)
	return context
