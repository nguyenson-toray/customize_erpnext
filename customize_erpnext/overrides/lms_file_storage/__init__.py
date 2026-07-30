# LMS File Storage Override Module
"""
LMSFileStorageOverride - Apply Monkey Patch

Ép ảnh/file upload qua nút Upload trong editor bài học LMS (Course Lesson) lưu vào
files/lms/{course}/{chapter}_{lesson}_{tên gốc} thay vì rơi thẳng public/files root
như mặc định. Mọi upload khác (Employee, Packing List, đính kèm document thường...)
không đổi hành vi — xem điều kiện trong lms_file_storage.py::_lms_upload_target.
"""

import frappe
from customize_erpnext.overrides.lms_file_storage.lms_file_storage import (
	custom_save_file_on_filesystem,
	custom_delete_file_from_filesystem,
)

try:
	from frappe.core.doctype.file.file import File

	# Lưu bản gốc để fallback cho mọi upload/xoá không phải Course Lesson (chỉ lưu 1 lần)
	if not hasattr(File, "_original_save_file_on_filesystem"):
		File._original_save_file_on_filesystem = File.save_file_on_filesystem
	if not hasattr(File, "_original_delete_file_from_filesystem"):
		File._original_delete_file_from_filesystem = File.delete_file_from_filesystem

	File.save_file_on_filesystem = custom_save_file_on_filesystem
	File.delete_file_from_filesystem = custom_delete_file_from_filesystem

	frappe.logger().info(
		"✅ File.save_file_on_filesystem / delete_file_from_filesystem monkey patched "
		"(LMS Course Lesson uploads -> files/lms/{course}/, xoá đúng path nhiều cấp)"
	)
except Exception as e:
	frappe.log_error(f"Failed to monkey patch File save/delete: {str(e)}", "LMS File Storage Monkey Patch Error")
	frappe.logger().error(f"Failed to monkey patch File save/delete: {str(e)}")
