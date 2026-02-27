import frappe


def get_context(context):
	# public page, no login required
	# if frappe.session.user == "Guest":
	# 	frappe.local.flags.redirect_location = "/login?redirect-to=/qr-code"
	# 	raise frappe.Redirect

	context.no_cache = 1
	return context
