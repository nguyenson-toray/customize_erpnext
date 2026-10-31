# Copyright (c) 2026, TIQN and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EmployeeSelfUpdateInfo(Document):
	def validate(self):
		from customize_erpnext.api.self_update_info.self_update_info_api import (
			apply_document_status,
			validate_desk_edit,
		)

		# Trang www (save_form_data) tự kiểm tra và đặt cờ này; mọi đường khác (form Desk,
		# API, Data Import) phải qua validate_desk_edit.
		if not (self.flags.from_portal or self.is_new()):
			validate_desk_edit(self)
		# Tình trạng hồ sơ (Đủ / Thiếu) luôn tính lại từ bản chụp hồ sơ trong data_json.
		apply_document_status(self)

	def on_update(self):
		from customize_erpnext.api.self_update_info.self_update_info_api import push_document_status_to_employee

		# Bản sao Document Status / Missing Documents trên Employee (tab Profile).
		push_document_status_to_employee(self)

	def on_trash(self):
		from customize_erpnext.api.self_update_info.self_update_info_api import clear_employee_document_status

		clear_employee_document_status(self)
