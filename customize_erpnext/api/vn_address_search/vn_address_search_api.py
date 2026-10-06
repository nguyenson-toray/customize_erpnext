# -*- coding: utf-8 -*-
# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Danh sách Tỉnh/Xã cho field **Autocomplete** + kiểm tra cặp (tỉnh, xã).

Đọc cùng 2 bảng thô `provinces` / `wards` mà `api/vn_address/import_vn_units.py` nạp từ GitHub.
Plan + bẫy: README.md cùng thư mục.

## 🔴 So khớp tên PHẢI là `COLLATE utf8mb4_bin`

Bảng dùng `utf8mb4_unicode_ci`, coi `Ơ = Ô` và `ạ = a`. Cùng tỉnh Quảng Ngãi có `Xã Ba Tơ`(21484)
và `Xã Ba Tô`(21523), `Xã Sơn Hà`(21289) và `Xã Sơn Hạ`(21292) — 8 cặp toàn quốc. So khớp bằng
collation mặc định sẽ coi đó là một xã. Tìm kiếm cho người dùng thì ngược lại: phải bỏ dấu, nhưng
việc đó làm ở client (`public/js/vn_address_autocomplete.js`).

## Không cache

Tỉnh 34 dòng, xã nhiều nhất 168 dòng/tỉnh — query < 1ms. Không cache thì không bao giờ trả dữ
liệu cũ sau khi chạy lại `import_vn_units`.
"""

import frappe
from frappe import _

# Loại địa chỉ trên Employee → (field tỉnh, field xã). Field tỉnh/xã lưu `full_name` (vd
# "Tỉnh Quảng Ngãi", "Xã Ba Tơ"), không lưu mã.
EMPLOYEE_ADDRESS_FIELDS = {
	"current": ("custom_current_address_province", "custom_current_address_commune"),
	"permanent": ("custom_permanent_address_province", "custom_permanent_address_commune"),
}


def _tables_ready():
	return bool(
		frappe.db.sql(
			"SELECT 1 FROM information_schema.tables "
			"WHERE table_schema = DATABASE() AND table_name = 'wards' LIMIT 1"
		)
	)


def _require_tables():
	if not _tables_ready():
		frappe.throw(_("Address data not imported yet. Run import_vn_units."))


def _province_code(province):
	"""Mã tỉnh từ mã hoặc full_name (so khớp phân biệt dấu). Không thấy → None."""
	if not province:
		return None
	province = province.strip()
	row = frappe.db.sql(
		"SELECT code FROM provinces "
		"WHERE code = %(p)s OR full_name = %(p)s COLLATE utf8mb4_bin LIMIT 1",
		{"p": province},
	)
	return row[0][0] if row else None


@frappe.whitelist(allow_guest=True)
def get_province_options():
	"""[{value, label, code}] — value = label = full_name. Sắp theo tên ngắn (bỏ "Tỉnh"/"Thành phố")."""
	_require_tables()
	rows = frappe.db.sql(
		"SELECT code, full_name FROM provinces ORDER BY name, code",
		as_dict=True,
	)
	return [{"value": r.full_name, "label": r.full_name, "code": r.code} for r in rows]


@frappe.whitelist(allow_guest=True)
def get_ward_options(province):
	"""[{value, label, code}] các xã của một tỉnh. `province` = mã hoặc full_name.

	Sắp theo tên ngắn để "Phường X" và "Xã X" nằm cạnh nhau theo chữ cái, thay vì dồn hết
	Phường lên trước Xã.
	"""
	_require_tables()
	code = _province_code(province)
	if not code:
		return []
	rows = frappe.db.sql(
		"SELECT code, full_name FROM wards WHERE province_code = %s ORDER BY name, code",
		(code,),
		as_dict=True,
	)
	return [{"value": r.full_name, "label": r.full_name, "code": r.code} for r in rows]


def get_address_error(province, ward):
	"""Lý do cặp (tỉnh, xã) không hợp lệ, hoặc None nếu hợp lệ / cả hai đều trống."""
	province = (province or "").strip()
	ward = (ward or "").strip()
	if not province and not ward:
		return None
	if ward and not province:
		return _("Please select a province before the ward")

	code = _province_code(province)
	if not code:
		return _("{0} is not a valid province").format(province)
	if not ward:
		return None

	found = frappe.db.sql(
		"SELECT 1 FROM wards WHERE province_code = %s AND full_name = %s COLLATE utf8mb4_bin LIMIT 1",
		(code, ward),
	)
	if not found:
		return _("{0} does not belong to {1}").format(ward, province)
	return None


@frappe.whitelist(allow_guest=True)
def check_address(province=None, ward=None):
	"""{valid, message} — cho client kiểm tra trước khi lưu."""
	_require_tables()
	message = get_address_error(province, ward)
	return {"valid": not message, "message": message}


def validate_employee_address(doc, method=None):
	"""Chốt chặn phía server cho Employee (Data Import / API / onboarding / self-update sync).

	Đăng ký riêng trong hooks.py `doc_events.Employee.validate` (không gọi từ
	`validate_employee_changes` vì hàm đó return sớm với hồ sơ mới).

	Chỉ kiểm khi hồ sơ mới hoặc địa chỉ vừa đổi: ~30 hồ sơ còn ghi tên tỉnh trước sáp nhập
	(`Tỉnh Quảng Nam`, `TP Đà Nẵng`…) vẫn phải lưu được khi HR sửa field khác.
	"""
	if not _tables_ready():
		return
	for province_field, ward_field in EMPLOYEE_ADDRESS_FIELDS.values():
		if not doc.meta.has_field(province_field):
			continue
		if not (
			doc.is_new()
			or doc.has_value_changed(province_field)
			or doc.has_value_changed(ward_field)
		):
			continue
		message = get_address_error(doc.get(province_field), doc.get(ward_field))
		if message:
			label = doc.meta.get_label(ward_field if doc.get(ward_field) else province_field)
			frappe.throw(f"{_(label)}: {message}", title=_("Invalid Address"))
