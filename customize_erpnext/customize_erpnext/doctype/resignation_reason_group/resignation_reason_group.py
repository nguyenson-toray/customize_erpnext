# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Nhóm lý do nghỉ việc — danh mục HR tự quản.

Tên bản ghi CHÍNH LÀ `group_name` (`autoname: field:group_name`), vì giá trị này được ghi thẳng
vào `Employee.custom_reason_for_leaving_group`. Đổi tên nhóm = rename bản ghi, và Frappe sẽ tự
cập nhật mọi Link trỏ tới nó.

Trước 21/08/2026 danh mục nằm trong `public/js/custom_scripts/employee_reason_for_leaving.json`
và chỉ IT sửa được.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class ResignationReasonGroup(Document):
	def on_trash(self):
		"""Không cho xoá nhóm còn lý do con — nếu không, các Link đó thành mồ côi."""
		used = frappe.db.count("Resignation Reason Group 2", {"reason_for_leaving_group": self.name})
		if used:
			frappe.throw(
				_("{0} reason(s) still belong to this group. Move or delete them first.").format(used),
				title=_("Group In Use"),
			)
