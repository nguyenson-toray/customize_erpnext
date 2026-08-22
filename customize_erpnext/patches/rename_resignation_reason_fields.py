# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Đổi tên 2 field của `Resignation Reason Group 2` cho khớp phần còn lại.

    reason        -> reason_for_leaving_group_2
    reason_group  -> reason_for_leaving_group

Sau lần này, **mọi nơi giữ một giá trị từ `Resignation Reason Group` đều tên
`reason_for_leaving_group`**, và từ `Resignation Reason Group 2` đều tên
`reason_for_leaving_group_2` — trên Employee, trên Resignation Application, và trong chính doctype
danh mục.

Đó không chỉ là cho đẹp: trước đây khoá filter (`reason_group`, field của danh mục) khác tên với
vế phải (`reason_for_leaving_group`, field của đơn) nên tìm-thay hàng loạt đổi nhầm hai lần liền,
sinh `Unknown column ... in 'WHERE'`. Cùng tên thì cái bẫy đó biến mất.

⚠ **post_model_sync** — `rename_field` cần field MỚI đã có trong meta và cột CŨ còn trong bảng.
⚠ `rename_field` **không xoá** cột cũ; patch tự xoá sau khi đối chiếu số dòng khớp.
"""

import frappe
from frappe.model.utils.rename_field import rename_field

DOCTYPE = "Resignation Reason Group 2"
RENAMES = [
	("reason", "reason_for_leaving_group_2"),
	("reason_group", "reason_for_leaving_group"),
]


def execute():
	if not frappe.db.table_exists(DOCTYPE):
		return

	for old, new in RENAMES:
		if not frappe.db.has_column(DOCTYPE, old):
			continue
		if not frappe.db.has_column(DOCTYPE, new):
			frappe.log_error(
				f"rename_resignation_reason_fields: chưa có cột {new}, bỏ qua {old}",
				"Resignation Reason rename",
			)
			continue

		rename_field(DOCTYPE, old, new)
		_drop_old_column(old, new)

	frappe.clear_cache(doctype=DOCTYPE)


def _drop_old_column(old: str, new: str):
	mismatch = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tab{DOCTYPE}`
		    WHERE IFNULL(`{old}`, '') <> '' AND IFNULL(`{new}`, '') <> IFNULL(`{old}`, '')"""
	)[0][0]
	if mismatch:
		frappe.log_error(
			f"{DOCTYPE}: {mismatch} dòng chưa copy được {old} -> {new}, GIỮ LẠI cột cũ",
			"Resignation Reason rename",
		)
		return
	frappe.db.sql_ddl(f"ALTER TABLE `tab{DOCTYPE}` DROP COLUMN `{old}`")
