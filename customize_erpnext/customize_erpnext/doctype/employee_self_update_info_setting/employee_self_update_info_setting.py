# Copyright (c) 2026, TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeSelfUpdateInfoSetting(Document):

	def validate(self):
		# Bypass code is compared against the 2-digit DOB input, so keep it 2 digits.
		if self.bypass_code and not (0 <= self.bypass_code <= 99):
			frappe.throw(_("Bypass Code must be a 2-digit number (0–99)."))

	def on_update(self):
		frappe.cache().delete_key("employee_self_update_info_config")

	@frappe.whitelist()
	def btn_add_by_date(self):
		"""Add employees filtered by date_of_joining / group / department / section."""
		if not (self.filter_date or self.group or self.department or self.custom_section):
			frappe.throw(
				_("Please choose at least one filter: Date of Joining, Group, Department or Section.")
			)

		filters = {"status": "Active"}
		if self.filter_date:
			filters["date_of_joining"] = self.filter_date
		if self.group:
			filters["custom_group"] = self.group
		if self.department:
			filters["department"] = self.department
		if self.custom_section:
			filters["custom_section"] = self.custom_section

		employees = frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name"],
			order_by="employee_name asc",
		)
		if not employees:
			frappe.msgprint(_("No employee matched the filter."))
			return

		existing_ids = {row.employee for row in (self.employees or [])}
		added = 0
		for emp in employees:
			if emp.name not in existing_ids:
				self.append("employees", {"employee": emp.name})
				added += 1

		if added:
			self.save()
			frappe.msgprint(_("Added {0} employee(s).").format(added))
		else:
			frappe.msgprint(_("All matched employees are already in the list."))

	@frappe.whitelist()
	def btn_clear_all(self):
		"""Clear the employees table and reset filters."""
		self.employees = []
		self.filter_date = None
		self.group = None
		self.department = None
		self.custom_section = None
		self.save()
		frappe.msgprint(_("Cleared the employee list and filters."))
