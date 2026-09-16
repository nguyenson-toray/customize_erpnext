# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Server side of the Điều hành xe page.

Two jobs: tell the page which controls to draw, and run the demo-data reset that
sits behind the Administrator-only button.
"""

import frappe
from frappe import _

SEED_EVENT = "tiqn_vehicle_seed_done"
SEED_LOCK = "tiqn_vehicle_seed_running"
SEED_LOCK_SECONDS = 1800


@frappe.whitelist(methods=["GET", "POST"])
def get_page_context():
	"""Which controls the page should draw for whoever just opened it."""
	frappe.has_permission("TIQN Vehicle Trip", throw=True)

	return {
		"can_dispatch": bool(frappe.has_permission("TIQN Vehicle Trip", "write")),
		"can_create_trip": bool(frappe.has_permission("TIQN Vehicle Trip", "create")),
		"can_manage_requests": bool(frappe.has_permission("TIQN Vehicle Request", "write")),
		"can_manage_vehicles": bool(frappe.has_permission("TIQN Vehicle", "write")),
		# The reset button wipes every trip and request. Administrator only - not
		# "System Manager", which several real people hold.
		"is_administrator": frappe.session.user == "Administrator",
	}


@frappe.whitelist(methods=["POST"])
def reset_demo_data(year=None, month=None):
	"""DELETE every trip and request, then rebuild a month of demo data.

	Returns immediately; the work runs on the `long` queue and announces itself on
	SEED_EVENT when it finishes.

	One month measures ~8.5s, so it would in fact survive an HTTP request today.
	It is backgrounded anyway: the cost scales with the range asked for (a year is
	twelve times the work), and this is a destructive bulk write - being SIGKILLed
	at the 120s gunicorn timeout would leave the fleet half-deleted and half-seeded
	with no way to tell which. A job that must finish does not ride on a request.
	"""
	if frappe.session.user != "Administrator":
		frappe.throw(_("Only Administrator can reset the demo data"), frappe.PermissionError)

	if frappe.cache.get_value(SEED_LOCK):
		frappe.throw(_("A reset is already running. Wait for it to finish."))

	# Expires on its own: if the worker is killed the lock must not wedge the
	# button forever.
	frappe.cache.set_value(SEED_LOCK, 1, expires_in_sec=SEED_LOCK_SECONDS)

	frappe.enqueue(
		"customize_erpnext.vehicle_management.page.vehicle_dispatch.vehicle_dispatch.run_reset_demo_data",
		queue="long",
		timeout=3600,
		user=frappe.session.user,
		year=year,
		month=month,
		enqueue_after_commit=True,
	)

	return {"queued": True, "message": _("Rebuilding the demo data in the background...")}


def run_reset_demo_data(user, year=None, month=None):
	"""Background half of reset_demo_data(). Never call this over HTTP."""
	from customize_erpnext.vehicle_management import seed_month

	try:
		kwargs = {"purge": True}
		if year:
			kwargs["year"] = int(year)
		if month:
			kwargs["month"] = int(month)

		summary = seed_month.execute(**kwargs)
		payload = {
			"success": True,
			"trips": summary["trips"],
			"requests": summary["requests"],
		}
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Vehicle demo data reset failed")
		payload = {"success": False, "error": frappe.get_traceback(limit=1)}
	finally:
		# `finally` does not run if the worker is SIGKILLed, which is exactly why
		# the lock carries its own expiry as well.
		frappe.cache.delete_value(SEED_LOCK)

	frappe.publish_realtime(SEED_EVENT, payload, user=user)
