# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Custom Field **virtual** trên Employee, link tới đơn nghỉ việc đã duyệt.

Giá trị do `CustomEmployee.custom_resignation_application` (property) trả về —
`overrides/employee/employee_override.py`. Frappe ưu tiên property trên class controller trước
khi thử `safe_eval` trên `options` (`frappe/model/base_document.py:541`), và với field kiểu `Link`
thì `options` đã dùng để chỉ doctype đích nên **bắt buộc** phải đi đường property.

⚠ `is_virtual = 1` nghĩa là **không có cột trong DB**: không lọc, không sắp xếp, không đưa vào
report được. Cần lọc theo đơn thì query thẳng `Resignation Application`.
"""

import frappe

FIELD = {
	"dt": "Employee",
	"fieldname": "custom_resignation_application",
	"label": "Resignation Application",
	"fieldtype": "Link",
	"options": "Resignation Application",
	"insert_after": "resignation_letter_date",
	"is_virtual": 1,
	"read_only": 1,
	"allow_on_submit": 0,
	"no_copy": 1,
	"print_hide": 1,
	"description": (
		"Đơn nghỉ việc đã duyệt của nhân viên này. Tra lại mỗi lần mở hồ sơ (virtual field, "
		"không lưu trong DB) nên rút đơn là link tự biến mất — không bao giờ lệch với đơn."
	),
}


def execute():
	name = frappe.db.get_value(
		"Custom Field", {"dt": FIELD["dt"], "fieldname": FIELD["fieldname"]}
	)
	if name:
		# Idempotent: chỉ đồng bộ lại thuộc tính, không tạo trùng.
		frappe.db.set_value("Custom Field", name, {
			k: v for k, v in FIELD.items() if k not in ("dt", "fieldname")
		})
	else:
		frappe.get_doc({"doctype": "Custom Field", **FIELD}).insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Employee")
