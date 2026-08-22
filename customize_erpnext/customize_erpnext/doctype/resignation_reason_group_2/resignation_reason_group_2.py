# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Lý do nghỉ việc — danh mục HR tự quản.

Tên bản ghi CHÍNH LÀ `reason` (`autoname: field:reason`), vì giá trị này được ghi thẳng vào
`Employee.custom_reason_for_leaving_group_2`.

⚠ Hệ quả: `reason` phải **duy nhất trên toàn danh mục**, không chỉ trong một nhóm. Hai nhóm
không thể cùng có "Vấn đề khác". Đây là đánh đổi có chủ ý: tên bản ghi đọc được bằng tiếng Việt
đáng giá hơn khả năng trùng tên giữa các nhóm, và danh mục hiện tại không có cặp nào trùng.

Bỏ tick `is_active` để ẩn khỏi ô chọn trên đơn mới; hồ sơ cũ đang dùng vẫn giữ nguyên giá trị.
Đó là lý do phải có cờ này thay vì xoá bản ghi.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class ResignationReasonGroup2(Document):
	def on_trash(self):
		"""Chặn xoá lý do đang được dùng — Link mồ côi làm form Employee báo lỗi."""
		refs = []

		employees = frappe.db.count("Employee", {"custom_reason_for_leaving_group_2": self.name})
		if employees:
			refs.append(_("{0} employee(s)").format(employees))

		apps = frappe.db.count(
			"Resignation Application",
			{"reason_for_leaving_group_2": self.name, "docstatus": ("<", 2)},
		)
		if apps:
			refs.append(_("{0} resignation application(s)").format(apps))

		if refs:
			frappe.throw(
				_("Still used by {0}. Untick Active to hide it from new records instead.").format(
					", ".join(refs)
				),
				title=_("Reason In Use"),
			)
