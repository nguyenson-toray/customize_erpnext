# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Employee overrides for the Vietnamese payroll.

Three changes:

1. `set_employee_name` — Full Name is the field people fill in; first/middle/last
   are derived from it, not the other way round.
2. `update_user_status` — maternity leave sets the employee Inactive, and that
   must not lock them out of their own account.
3. `custom_resignation_application` — virtual Link back to the submitted
   Resignation Application (see the property below).
4. `validate` — dựng `permanent_address` / `current_address` bằng tiếng Anh từ bộ field
   `custom_*_address_*` tiếng Việt (xem `employee_address.py`).

Extends HRMS's `EmployeeMaster`, not ERPNext's `Employee`: HRMS already claims
`override_doctype_class["Employee"]`, and `customize_erpnext` loads after it, so
subclassing core directly would silently drop HRMS's Employee naming.
"""

import frappe
from hrms.overrides.employee_master import EmployeeMaster

from customize_erpnext.api.employee.employee_validation import split_employee_name_parts
from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync import (
	is_inactive_for_maternity,
)
from customize_erpnext.overrides.employee.employee_address import sync_english_addresses


class CustomEmployee(EmployeeMaster):
	def validate(self):
		"""Như core, cộng thêm bản tiếng Anh của hai địa chỉ.

		Đặt ở controller chứ không ở JS: Data Import và API không đi qua JS, mà phần lớn địa chỉ
		trên site này vào bằng Data Import.
		"""
		super().validate()
		sync_english_addresses(self)

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

	# ------------------------------------------------------------------ virtual
	@property
	def custom_resignation_application(self):
		"""Đơn nghỉ việc ĐÃ DUYỆT của nhân viên này, hoặc `None`.

		Là **virtual field** (`Custom Field.is_virtual = 1`): không có cột trong DB, giá trị tra
		lại mỗi lần mở hồ sơ. Frappe ưu tiên `@property` trên class controller trước khi thử
		`safe_eval` trên `options` (`frappe/model/base_document.py:541`) — bắt buộc phải đi đường
		property ở đây, vì với field kiểu `Link` thì `options` đã dùng để chỉ doctype đích rồi.

		Vì sao virtual chứ không phải cột thật ghi lúc submit:

		1. **Không bao giờ lệch.** Rút đơn, xoá đơn, amend — link tự đúng theo `docstatus`, không
		   cần hook dọn ở từng nhánh. Một cột thật thì mỗi đường thoát là một chỗ phải nhớ xoá.
		2. **Không đụng vào Employee.** Ghi thêm một cột nghĩa là mỗi lần submit/cancel đơn lại
		   `set_value` lên hồ sơ nhân viên, kéo theo `modified` và cache — trong khi thông tin này
		   vốn suy được.

		⚠ Đánh đổi: **không lọc / không sắp xếp / không đưa vào report được**, vì không có cột.
		Cần lọc theo đơn thì query thẳng `Resignation Application`.

		⚠ `docstatus = 1` là điều kiện duy nhất. Đơn Draft chưa duyệt thì chưa có gì để hiện, đơn
		Cancelled là đơn **đã rút** — hiện lên sẽ khiến người đọc tưởng nhân viên đang nghỉ việc.

		`order_by` viết tường minh: `validate_no_other_application` đã bảo đảm nhiều nhất một đơn
		submitted mỗi người, nhưng mặc định của `get_all` không có thứ tự bảo đảm và một ngày nào
		đó ràng buộc kia nới ra thì chỗ này phải vẫn tất định.
		"""
		if not self.name or self.is_new():
			return None

		rows = frappe.get_all(
			"Resignation Application",
			filters={"employee": self.name, "docstatus": 1},
			pluck="name",
			order_by="relieving_date desc, creation desc",
			limit=1,
		)
		return rows[0] if rows else None
