# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt
"""Employee Transfer override — restrict properties, allow historical records.

See work_history.py for why the timeline is rebuilt instead of appended to.
"""

from hrms.hr.doctype.employee_transfer.employee_transfer import EmployeeTransfer

from .work_history import (
	ENFORCE_EFFECTIVE_DATE_NOT_FUTURE,
	autofill_property_rows,
	rebuild_work_history,
	validate_allowed_fields,
	validate_link_values,
)


class CustomEmployeeTransfer(EmployeeTransfer):
	@property
	def is_inter_company(self) -> bool:
		"""True when the stock HRMS flow has to run instead of a plain property update.

		Both branches relieve or clone the employee record and rewrite date_of_joining,
		which is far more than a work-history rebuild. TIQN is a single company so
		neither is used in practice, but leaving them on the HRMS code path means the
		override never has to reimplement them.
		"""
		return bool(self.create_new_employee_id) or bool(
			self.new_company and self.new_company != self.company
		)

	def validate(self):
		# autofill first: it resolves `fieldname` from the `property` label, which
		# validate_allowed_fields then checks against the allow-list.
		autofill_property_rows(self)
		validate_allowed_fields(self)
		validate_link_values(self)

	def before_submit(self):
		if ENFORCE_EFFECTIVE_DATE_NOT_FUTURE:
			super().before_submit()

	def on_submit(self):
		if self.is_inter_company:
			super().on_submit()
			return

		rebuild_work_history(self.employee)

	def on_cancel(self):
		if self.is_inter_company:
			super().on_cancel()
			return

		rebuild_work_history(
			self.employee,
			revert=self,
			exclude=(self.doctype, self.name),
		)
