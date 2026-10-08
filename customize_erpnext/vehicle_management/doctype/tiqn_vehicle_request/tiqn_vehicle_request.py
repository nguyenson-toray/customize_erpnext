# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

# pending -> assigned (creating the trip IS the approval - see
# vehicle_management/API_CONTRACT.md mục 6), or pending -> rejected. `approved` is kept as a
# legal middle step for the Desk UI, but the Mini App no longer produces it.
#
# `cancelled` is the requester calling the ride off and is reachable from any
# state that has not finished yet - plans change after a vehicle is assigned just
# as often as before. `rejected` (dispatcher says no) and `cancelled` (requester
# backs out) are deliberately different states: the reports have to tell them apart.
#
# Kept here (not only in the API) so a Dispatcher editing the form in Desk
# cannot produce a state the Zalo Mini App does not understand.
ALLOWED_TRANSITIONS = {
	"pending": {"pending", "approved", "assigned", "rejected", "cancelled"},
	"approved": {"approved", "assigned", "rejected", "cancelled"},
	"assigned": {"assigned", "cancelled"},
	"rejected": {"rejected"},
	"cancelled": {"cancelled"},
}

# Details of the ride itself, as opposed to the workflow fields (status,
# rejection_reason, assigned_trip). Frozen once a dispatcher has acted on the
# request - see freeze_content_once_acted_on().
CONTENT_FIELDS = (
	"from_location", "to_location", "request_time", "return_time",
	"purpose", "passenger_count", "notes", "employee_id_display",
	"employee_name", "zalo_user_id",
)


class TIQNVehicleRequest(Document):
	def before_insert(self):
		if not self.submit_time:
			self.submit_time = now_datetime()
		if not self.status:
			self.status = "pending"

	def validate(self):
		self.validate_status_transition()
		self.freeze_content_once_acted_on()
		self.validate_return_time()

		if self.status == "rejected" and not self.rejection_reason:
			frappe.throw(_("Rejection Reason is required when rejecting a request"))

		if self.status == "assigned" and not self.assigned_trip:
			frappe.throw(_("A request can only be assigned when it is linked to a trip"))

		if self.status != "rejected":
			self.rejection_reason = None

		if not self.passenger_count or self.passenger_count < 1:
			self.passenger_count = 1

	def freeze_content_once_acted_on(self):
		"""Once a request is past `pending`, its ride details stop being editable.

		A dispatcher has already read "Toray VSIP -> airport, 14:00" and sent a
		driver on it. Letting the pickup point change afterwards, silently, sends
		that driver to the wrong place - and nothing on the trip would show it had
		moved.

		🔴 This rule used to live ONLY in update_request(). Measured 22/09/2026 with
		the Mini App's own API key: a plain
		`PUT /api/resource/TIQN Vehicle Request/<name>` changed `from_location` on a
		request already ASSIGNED to a trip, no error, no trace. A rule that lives in
		one endpoint is not a rule - the DocType is reachable over REST, and the key
		ships inside the client.

		The dispatcher editing the Desk form is subject to it too, on purpose: if the
		pickup really has moved, the trip is what needs changing
		(update_trip_route(), which flags route_changed and makes the driver
		acknowledge it), not the paperwork behind it.
		"""
		if self.is_new():
			return

		previous = self.get_doc_before_save()
		# 🔴 The status BEFORE this save is what decides, not the one being written.
		# A requester who changes their mind sends "notes + status=cancelled" in ONE
		# call; reading the new status would reject their own cancellation. Same
		# semantics update_request() has always had.
		if not previous or previous.status == "pending":
			return

		changed = [f for f in CONTENT_FIELDS if (self.get(f) or None) != (previous.get(f) or None)]
		if changed:
			frappe.throw(
				_("Request {0} is already {1} - its details can no longer be changed ({2}). "
				  "To move a trip that has already been arranged, change the trip.").format(
					self.name, _(self.status), ", ".join(changed)
				)
			)

	def validate_return_time(self):
		if not self.return_time or not self.request_time:
			return

		if get_datetime(self.return_time) <= get_datetime(self.request_time):
			frappe.throw(_("Return Time must be later than Request Time"))

	def validate_status_transition(self):
		if self.is_new():
			return

		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return

		allowed = ALLOWED_TRANSITIONS.get(previous.status, set())
		if self.status not in allowed:
			frappe.throw(
				_("Cannot change request status from {0} to {1}").format(
					previous.status, self.status
				)
			)
