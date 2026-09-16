# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TIQNFixedTripSchedule(Document):
	def validate(self):
		if self.from_location and self.to_location and self.from_location == self.to_location:
			frappe.throw(_("From Location and To Location must be different"))
