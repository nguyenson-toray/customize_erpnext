"""Chuyển `Attendance Calculation Setting.exclude_employee_ids` (Small Text, gõ tay)
sang bảng con `exclude_employees` (Table MultiSelect → Link Employee).

Vì sao đổi: gõ sai mã trong ô text **hỏng trong im lặng** — không ai bị loại, không có
lỗi nào. Mà danh sách này chi phối cùng lúc engine tính công, Net Headcount, daily
email và Export Excel, nên một lỗi gõ làm sai lệch cả bốn.

🔴 Chiều ngược lại cũng nguy hiểm: patch làm MẤT giá trị thì cả bốn nơi đồng loạt nới
rộng phạm vi, cũng trong im lặng. Vì vậy patch đếm vào/ra và THROW nếu lệch, thà dừng
migrate còn hơn chạy tiếp với danh sách rỗng.

Idempotent: chạy lại thì không thêm trùng, và mã đã có trong bảng con thì bỏ qua.
"""

import re

import frappe

SETTING = "Attendance Calculation Setting"
LEGACY_FIELD = "exclude_employee_ids"


def execute():
	frappe.reload_doc("customize_erpnext", "doctype", "attendance_excluded_employee")
	frappe.reload_doc("customize_erpnext", "doctype", "attendance_calculation_setting")

	# Đọc thẳng `tabSingles`: field cũ đã bị gỡ khỏi doctype nên không còn trong meta.
	# 🔴 KHÔNG dùng `get_single_value()` — hàm đó kiểm tra meta và throw
	# `Field ... does not exist` đúng trong tình huống này.
	from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
		_legacy_exclude_text,
	)

	raw = _legacy_exclude_text()
	legacy_ids = [p.strip() for p in re.split(r"[,\s]+", str(raw)) if p.strip()]

	doc = frappe.get_doc(SETTING)
	existing = {(r.employee or "").strip() for r in (doc.get("exclude_employees") or [])}

	missing, added = [], 0
	for emp in legacy_ids:
		if emp in existing:
			continue
		if not frappe.db.exists("Employee", emp):
			# Link không nhận mã không tồn tại. Không tự bịa: báo ra để người sửa tay.
			missing.append(emp)
			continue
		doc.append("exclude_employees", {"employee": emp})
		existing.add(emp)
		added += 1

	if added:
		doc.save(ignore_permissions=True)

	final = {
		(r.employee or "").strip()
		for r in frappe.get_doc(SETTING).get("exclude_employees") or []
	}

	if missing:
		frappe.throw(
			f"{SETTING}: {len(missing)} mã trong `{LEGACY_FIELD}` không tồn tại trong "
			f"tabEmployee nên không chuyển được sang Link: {', '.join(missing)}. "
			"Sửa tay danh sách rồi chạy lại patch."
		)

	if set(legacy_ids) - final:
		frappe.throw(
			f"{SETTING}: chuyển thiếu. Vào {len(set(legacy_ids))}, ra {len(final)}, "
			f"thiếu: {', '.join(sorted(set(legacy_ids) - final))}"
		)

	# Chỉ xoá dòng cũ khi đã chắc chắn không mất gì. Field kiểu Table không lưu ở
	# `tabSingles`, nên dòng này còn lại là rác nằm vĩnh viễn.
	if raw:
		frappe.db.delete("Singles", {"doctype": SETTING, "field": LEGACY_FIELD})

	frappe.db.commit()
	print(f"   ✓ exclude_employees: {len(legacy_ids)} mã cũ → {len(final)} dòng (thêm mới {added})")
