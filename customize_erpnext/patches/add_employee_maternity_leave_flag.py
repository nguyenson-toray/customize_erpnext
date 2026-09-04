"""Thêm `Employee.custom_is_maternity_leave` và nạp giá trị lần đầu.

Vì sao cần một cột THẬT trên Employee, trong khi `Employee Maternity.status` đã có
sẵn thông tin đó: Number Card và Dashboard Chart kiểu "Document Type" chỉ lọc được
field nằm trên **chính doctype** của chúng — không join sang doctype khác. Không có
cột này thì 7 chart/card đếm nhân viên (Total Employees, Department Wise Employee
Count, Gender Diversity Ratio…) không có cách nào trừ người đang nghỉ thai sản.

Idempotent: chạy lại bao nhiêu lần cũng ra cùng kết quả.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	create_custom_field(
		"Employee",
		{
			"fieldname": "custom_is_maternity_leave",
			"label": "Is Maternity Leave",
			"fieldtype": "Check",
			"insert_after": "custom_sub_status",
			"read_only": 1,
			"in_standard_filter": 1,
			"default": "0",
			"description": (
				"Set automatically from Employee Maternity — do not edit. "
				"Reflects TODAY only; period reports must read the maternity date range."
			),
		},
	)

	from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync import (
		sync_all_maternity_flags,
	)

	result = sync_all_maternity_flags()
	frappe.db.commit()
	print(f"   ✓ cờ thai sản: bật {result['set']}, gỡ {result['cleared']}")
