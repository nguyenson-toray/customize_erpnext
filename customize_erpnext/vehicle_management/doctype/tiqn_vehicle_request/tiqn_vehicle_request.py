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
# rejection_reason, assigned_trip). Editable through the API only while the
# request is still pending - see update_request().
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
		self.validate_return_time()

		if self.status == "rejected" and not self.rejection_reason:
			frappe.throw(_("Rejection Reason is required when rejecting a request"))

		if self.status == "assigned" and not self.assigned_trip:
			frappe.throw(_("A request can only be assigned when it is linked to a trip"))

		if self.status != "rejected":
			self.rejection_reason = None

		if not self.passenger_count or self.passenger_count < 1:
			self.passenger_count = 1

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
