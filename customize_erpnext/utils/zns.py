# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Zalo ZNS notifications for the Vehicle Management module - Phase 2.

DISARMED ON PURPOSE. Nothing in this app calls send_zns(); the only caller today
is a manual bench execute. Three separate things must be true before a single
message leaves this site:

  1. site_config.json has `zalo_zns_enabled: 1`   (default: absent -> off)
  2. site_config.json has `zalo_oa_access_token`  (default: absent -> off)
  3. site_config.json has the template id for the event you are sending

That mirrors the app-wide rule for outbound messaging: a notification channel is
created switched off with no recipients, and a human decides when it goes live
and who it reaches. A vehicle dispatch system messages real drivers and real
employees on their personal phones - an accidental bulk run is not recoverable.

Templates to register with the Zalo OA (see vehicle_management/README.md sec. 8):

  | Event           | Recipient  | Variables                                              |
  |-----------------|------------|--------------------------------------------------------|
  | new request     | Dispatcher | employee_name, from_location, to_location, request_time |
  | trip assigned   | Requester  | vehicle_name, driver_name, depart_time                  |
  | request rejected| Requester  | rejection_reason                                        |
  | route changed   | Driver     | from_location, to_location, dispatcher_note             |
"""

import frappe
from frappe import _

ZNS_ENDPOINT = "https://business.openapi.zalo.me/message/template"

# site_config key -> the event it covers. Kept here so a half-configured site
# fails loudly on the missing key instead of silently sending nothing.
TEMPLATE_KEYS = {
	"new_request": "zalo_zns_template_new_request",
	"trip_assigned": "zalo_zns_template_trip_assigned",
	"request_rejected": "zalo_zns_template_request_rejected",
	"route_changed": "zalo_zns_template_route_changed",
}


def is_enabled() -> bool:
	"""True only when an admin has explicitly switched ZNS on for this site."""
	return bool(frappe.conf.get("zalo_zns_enabled")) and bool(
		frappe.conf.get("zalo_oa_access_token")
	)


def send_zns(phone, template_id, template_data, dry_run=True):
	"""Send one ZNS message.

	dry_run defaults to True: the payload is logged and returned, nothing leaves
	the server. Pass dry_run=False deliberately, and only after the OA package is
	live and the recipient list has been agreed with the business owner.
	"""
	if not phone:
		frappe.throw(_("A phone number is required to send a ZNS message"))

	payload = {
		"phone": phone,
		"template_id": template_id,
		"template_data": template_data or {},
		"tracking_id": frappe.generate_hash(length=10),
	}

	if dry_run or not is_enabled():
		frappe.logger("zns").info({"dry_run": True, "payload": payload})
		return {"sent": False, "reason": "dry_run" if dry_run else "zns_disabled", "payload": payload}

	import requests

	response = requests.post(
		ZNS_ENDPOINT,
		json=payload,
		headers={"access_token": frappe.conf.get("zalo_oa_access_token")},
		timeout=20,
	)
	result = response.json()
	frappe.logger("zns").info({"dry_run": False, "tracking_id": payload["tracking_id"], "result": result})
	return {"sent": response.ok, "result": result}


def get_template_id(event):
	key = TEMPLATE_KEYS.get(event)
	if not key:
		frappe.throw(_("Unknown ZNS event: {0}").format(event))

	template_id = frappe.conf.get(key)
	if not template_id:
		frappe.throw(_("site_config.json is missing {0} - ZNS for {1} is not configured").format(key, event))
	return template_id
