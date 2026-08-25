# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
"""Employee Promotion override — restrict properties, allow historical records.

See work_history.py for why the timeline is rebuilt instead of appended to.
"""

import frappe

from hrms.hr.doctype.employee_promotion.employee_promotion import EmployeePromotion

from .work_history import (
	ENFORCE_EFFECTIVE_DATE_NOT_FUTURE,
	autofill_property_rows,
	rebuild_work_history,
	validate_allowed_fields,
	validate_link_values,
)


class CustomEmployeePromotion(EmployeePromotion):
	def validate(self):
		# HRMS calls validate_active_employee() here, which throws for any Inactive
		# employee. Promotions that happened in the past still have to be recordable for
		# people who are now on maternity leave (Inactive) or have already left, so the
		# check is deliberately dropped.

		# autofill first: it resolves `fieldname` from the `property` label, which
		# validate_allowed_fields then checks against the allow-list.
		autofill_property_rows(self)
		validate_allowed_fields(self)
		validate_link_values(self)

	def before_submit(self):
		if ENFORCE_EFFECTIVE_DATE_NOT_FUTURE:
			super().before_submit()

	def on_submit(self):
		if self.revised_ctc:
			frappe.db.set_value("Employee", self.employee, "ctc", self.revised_ctc)

		rebuild_work_history(self.employee)

	def on_cancel(self):
		if self.revised_ctc:
			frappe.db.set_value("Employee", self.employee, "ctc", self.current_ctc)

		rebuild_work_history(
			self.employee,
			revert=self,
			exclude=(self.doctype, self.name),
		)
