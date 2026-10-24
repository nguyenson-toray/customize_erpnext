# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from customize_erpnext.employee_portal.notify import TARGET_SCREEN


class TIQNPortalNotification(Document):
	"""One row per notification, whoever receives it: `All` (whole company) or
	`Employees` (picked in the Table MultiSelect). No per-person read state - the
	Mini App's unread count uses TIQN Portal Account.notifications_seen_on."""

	def validate(self):
		# HR typing one on the Desk only picks a type: derive where the Mini App opens it.
		if not self.target_screen:
			self.target_screen = TARGET_SCREEN.get(self.type, "NONE")
		if self.audience == "All":
			self.set("employees", [])
			return
		seen, rows = set(), []
		for row in self.employees or []:
			if row.employee and row.employee not in seen:
				seen.add(row.employee)
				rows.append(row)
		self.set("employees", rows)
		if not rows:
			frappe.throw(_("Pick at least one employee, or set Audience to All."))
