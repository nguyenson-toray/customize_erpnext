# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Một người phụ thuộc trong hồ sơ NPT của nhân viên.

Toàn bộ kiểm tra nằm ở doctype cha `Employee Dependent` — child doctype không có
`validate()` riêng khi lưu qua form cha.
"""

from frappe.model.document import Document


class EmployeeDependentItem(Document):
	pass
