# Copyright (c) 2026, TIQN and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EmployeeSelfUpdateInfo(Document):
	def validate(self):
		# Trang www (save_form_data) tự kiểm tra và đặt cờ này; mọi đường khác (form Desk,
		# API, Data Import) phải qua validate_desk_edit.
		if self.flags.from_portal or self.is_new():
			return
		from customize_erpnext.api.self_update_info.self_update_info_api import validate_desk_edit

		validate_desk_edit(self)
