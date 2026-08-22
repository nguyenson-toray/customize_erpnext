# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Đổi tên 3 field của `Resignation Application` cho khớp với Employee.

    posting_date  -> resignation_letter_date        (Employee.resignation_letter_date)
    reason_group  -> reason_for_leaving_group       (Employee.custom_reason_for_leaving_group)
    reason        -> reason_for_leaving_group_2     (Employee.custom_reason_for_leaving_group_2)

Bỏ tiền tố `custom_` vì đây là doctype của chính app — `custom_` chỉ dành cho Custom Field cắm
vào doctype lõi.

## Vì sao phải là patch, không chỉ sửa file JSON

Đổi `fieldname` trong JSON rồi `migrate` suông thì schema sync **tạo cột mới rỗng** và **bỏ lại
dữ liệu ở cột cũ** — im lặng, không báo gì. Site đang có 1.258 đơn.

`frappe.model.rename_field` copy dữ liệu sang cột mới, đồng thời cập nhật Property Setter,
User Settings và các Report Builder trỏ tới tên cũ.

⚠ **post_model_sync**: `rename_field` yêu cầu field MỚI đã có trong meta và cột CŨ còn trong
bảng — đúng trạng thái sau khi schema sync chạy xong.

⚠ `rename_field` **không xoá** cột cũ. Patch tự xoá, nhưng chỉ sau khi đã đối chiếu số dòng khớp.
"""

import frappe
from frappe.model.utils.rename_field import rename_field

DOCTYPE = "Resignation Application"
RENAMES = [
	("posting_date", "resignation_letter_date"),
	("reason_group", "reason_for_leaving_group"),
	("reason", "reason_for_leaving_group_2"),
]


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return

	for old, new in RENAMES:
		has_old = frappe.db.has_column(DOCTYPE, old)
		has_new = frappe.db.has_column(DOCTYPE, new)

		if not has_old:
			continue  # đã đổi ở lần chạy trước, hoặc site mới dựng thẳng tên mới
		if not has_new:
			frappe.log_error(
				f"rename_resignation_application_fields: chưa có cột {new}, bỏ qua {old}",
				"Resignation Application rename",
			)
			continue

		rename_field(DOCTYPE, old, new)
		_drop_old_column(old, new)

	frappe.clear_cache(doctype=DOCTYPE)


def _drop_old_column(old: str, new: str):
	"""Xoá cột cũ — chỉ khi đã chắc dữ liệu nằm trọn ở cột mới.

	Đối chiếu số dòng có giá trị ở hai cột trước khi xoá: `rename_field` chạy bằng một câu
	`UPDATE ... SET new = old`, nếu vì lý do gì đó nó không chạm được dòng nào thì xoá cột cũ là
	mất dữ liệu vĩnh viễn.
	"""
	mismatch = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tab{DOCTYPE}`
		    WHERE IFNULL(`{old}`, '') <> '' AND IFNULL(`{new}`, '') <> IFNULL(`{old}`, '')"""
	)[0][0]

	if mismatch:
		frappe.log_error(
			f"{DOCTYPE}: {mismatch} dòng chưa copy được {old} -> {new}, GIỮ LẠI cột cũ",
			"Resignation Application rename",
		)
		return

	frappe.db.sql_ddl(f"ALTER TABLE `tab{DOCTYPE}` DROP COLUMN `{old}`")
