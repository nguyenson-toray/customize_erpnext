# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TIQNZaloRoleMap(Document):
	def validate(self):
		self.zalo_user_id = (self.zalo_user_id or "").strip()
		if not self.zalo_user_id:
			frappe.throw(_("Zalo User ID is required"))

		if self.role == "driver" and not self.driver_ref:
			frappe.throw(_("Driver is required when role is driver"))

		if self.role != "driver":
			self.driver_ref = None
