# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours


class OvertimeRegistration(Document):
	def validate(self):
		self.calculate_totals_and_apply_reason()

	def calculate_totals_and_apply_reason(self):
		if not self.ot_employees:
			self.total_employees = 0
			self.total_hours = 0
			return

		distinct_employees = set()
		total_hours = 0.0

		for d in self.ot_employees:
			if d.employee:
				distinct_employees.add(d.employee)

			if d.get("from") and d.get("to"):
				total_hours += time_diff_in_hours(d.to, d.get("from"))

			if self.reason_general and not d.reason:
				d.reason = self.reason_general

		self.total_employees = len(distinct_employees)
		self.total_hours = total_hours