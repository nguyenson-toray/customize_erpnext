# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Employee overrides for the Vietnamese payroll.

Two changes, both replacing core behaviour that assumes a Western name model or a
Western leave model:

1. `set_employee_name` — Full Name is the field people fill in; first/middle/last
   are derived from it, not the other way round.
2. `update_user_status` — maternity leave sets the employee Inactive, and that
   must not lock them out of their own account.

Extends HRMS's `EmployeeMaster`, not ERPNext's `Employee`: HRMS already claims
`override_doctype_class["Employee"]`, and `customize_erpnext` loads after it, so
subclassing core directly would silently drop HRMS's Employee naming.
"""

from hrms.overrides.employee_master import EmployeeMaster

from customize_erpnext.api.employee.employee_validation import split_employee_name_parts
from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync import (
	is_inactive_for_maternity,
)


class CustomEmployee(EmployeeMaster):
	def set_employee_name(self):
		"""Derive first/middle/last from Full Name — the reverse of core.

		Core joins first + middle + last over `employee_name`, which quietly threw
		away any full name set without also setting the three parts: renaming an
		employee through Data Import or the API changed nothing at all, because the
		join ran first and put the old name straight back.

		Vietnamese records only ever carry a full name, so that direction is wrong
		here. The three fields stay populated because ERPNext and HRMS still read
		them (User creation, the holiday reminder greeting), but they are now
		output, not input, and are hidden from the form.

		Falls back to core when there is no full name to work from — that is a
		record built the core way, first name first.
		"""
		if self.employee_name and self.employee_name.strip():
			# Collapse stray double spaces so the parts split predictably
			self.employee_name = " ".join(self.employee_name.split())
			(
				self.first_name,
				self.middle_name,
				self.last_name,
			) = split_employee_name_parts(self.employee_name)
		else:
			super().set_employee_name()

	def update_user_status(self):
		"""Như core, nhưng bỏ qua khi Inactive là do nghỉ thai sản."""
		if (
			self.status == "Inactive"
			and self.user_id
			and is_inactive_for_maternity(self.name)
		):
			return

		super().update_user_status()
