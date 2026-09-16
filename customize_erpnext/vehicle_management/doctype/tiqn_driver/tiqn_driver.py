# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class TIQNDriver(Document):
	def validate(self):
		self.zalo_user_id = (self.zalo_user_id or "").strip() or None
		if self.zalo_user_id:
			clash = frappe.db.get_value(
				"TIQN Driver",
				{"zalo_user_id": self.zalo_user_id, "name": ("!=", self.name)},
				"name",
			)
			if clash:
				frappe.throw(
					_("Zalo User ID {0} is already used by driver {1}").format(
						self.zalo_user_id, clash
					)
				)
