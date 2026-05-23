# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EmployeeSelfUpdateSetting(Document):

	def on_update(self):
		frappe.cache().delete_key("employee_self_update_config")

	@frappe.whitelist()
	def btn_add_by_date(self):
		"""Add employees filtered by date_of_joining and/or custom_group (at least one required)."""
		if not self.filter_date and not self.group:
			frappe.throw(_("Vui lòng chọn ít nhất một bộ lọc: Ngày nhận việc hoặc Group."))

		filters = {"status": "Active"}
		if self.filter_date:
			filters["date_of_joining"] = self.filter_date
		if self.group:
			filters["custom_group"] = self.group

		employees = frappe.get_all(
			"Employee",
			filters=filters,
			fields=["name", "employee_name"],
			order_by="employee_name asc",
		)

		if not employees:
			frappe.msgprint(_("Không tìm thấy nhân viên nào phù hợp với bộ lọc."))
			return

		existing_ids = {row.employee for row in (self.employees or [])}
		added = 0
		for emp in employees:
			if emp.name not in existing_ids:
				self.append("employees", {"employee": emp.name})
				added += 1

		if added:
			self.save()
			frappe.msgprint(_("Đã thêm {0} nhân viên.").format(added))
		else:
			frappe.msgprint(_("Tất cả nhân viên này đã có trong danh sách."))

	@frappe.whitelist()
	def btn_clear_all(self):
		"""Clear the employees table and reset filters."""
		self.employees = []
		self.filter_date = None
		self.group = None
		self.save()
		frappe.msgprint(_("Đã xóa toàn bộ danh sách nhân viên và bộ lọc."))

	@frappe.whitelist()
	def btn_reset_config(self):
		"""Reset field_config_json to default from config file."""
		import json
		import os

		config_path = os.path.join(
			os.path.dirname(__file__), "employee_self_update_config.json"
		)
		with open(config_path, "r", encoding="utf-8") as f:
			default_config = f.read()

		self.field_config_json = default_config
		self.save()
		frappe.msgprint(_("Đã reset config về mặc định."))
