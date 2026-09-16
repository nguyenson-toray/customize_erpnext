import frappe

# Where the dashboard actually lives. It is a Desk page because it needs
# frappe.ui.Dialog, frappe.datetime and frappe.call - none of which exist on a
# www page (a portal template has no `frappe` JS object at all).
# NOT "/app/vehicle": ERPNext already ships a `Vehicle` DocType (module Setup),
# and /app/vehicle is its list view. A Page of the same name fights it for the
# route, so the page is called vehicle-dispatch and /vehicle points here.
TARGET = "/app/vehicle-dispatch"
REQUIRED_ROLES = {"Vehicle Manager", "System Manager"}


def get_context(context):
	"""Make the short URL /vehicle work.

	vehicle_management/README.md mục 17 asks for the page at /vehicle, but a
	Frappe Desk page is only ever served from /app/<name> - a bare /vehicle
	returns 404. This redirects instead of duplicating the page as a portal
	template, so there is still exactly one dashboard to maintain.
	"""
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = f"/login?redirect-to={TARGET}"
		raise frappe.Redirect

	if not REQUIRED_ROLES & set(frappe.get_roles()):
		raise frappe.PermissionError(
			frappe._("You do not have permission to access the vehicle dashboard")
		)

	frappe.local.flags.redirect_location = TARGET
	raise frappe.Redirect
