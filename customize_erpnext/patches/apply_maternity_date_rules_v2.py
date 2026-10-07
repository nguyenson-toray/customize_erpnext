"""Áp quy tắc ngày thai sản mới (user chốt 07/10/2026) cho MỌI hồ sơ — giai đoạn liên tục.

  Pregnant To trống → Estimated Due Date
  Maternity From = Pregnant To + 1 (có sẵn Maternity From thì giữ, Pregnant To = -1)
  Maternity To = Maternity From + Leave Months - 1;  Young Child From = Maternity To + 1
  Young Child To = Date of Birth + 364, chưa có ngày sinh → trống

Hồ sơ có `leave_months = 0` (ngày kết thúc lẻ, không tròn tháng) → làm tròn về số tháng
GẦN NHẤT rồi tính lại theo quy tắc, để kỳ hiện tại là chuẩn.

⚠ Hồ sơ CHƯA có Maternity From (57 lúc 07/10/2026) GIỮ NGUYÊN — user chốt "không làm gì":
trống = không có nghỉ thai sản (sẩy thai / không sinh, HR ghi Note). Muốn vậy, mỗi doc được
gắn `_doc_before_save` = chính nó để `has_value_changed()` thấy "không đổi gì" → controller
không tự điền Maternity From (chỉ điền khi tạo mới / HR sửa Pregnant To).

Cuối cùng DROP cột `maternity_from_date_estimate` (field đã xoá khỏi DocType, 0 hồ sơ có dữ
liệu; Frappe không tự xoá cột khi gỡ field).

Chỉ ghi field đổi, bằng `db.set_value(update_modified=False)` — không chạy hook/recalc
attendance. Sau đó tính lại status + cờ thai sản trên Employee (`calculate_all_maternity_statuses`).
Idempotent.

Dry-run: bench --site <site> execute customize_erpnext.patches.apply_maternity_date_rules_v2.execute --kwargs "{'dry_run': 1}"
"""

from collections import Counter

import frappe
from dateutil.relativedelta import relativedelta
from frappe.utils import add_days, getdate

FIELDS = (
	"pregnant_to_date", "maternity_from_date", "leave_months", "maternity_to_date",
	"youg_child_from_date", "youg_child_to_date",
)


def _nearest_months(mat_from, mat_to):
	rd = relativedelta(add_days(getdate(mat_to), 1), getdate(mat_from))
	months = rd.years * 12 + rd.months + (1 if rd.days >= 15 else 0)
	return max(months, 1)


def execute(dry_run=0):
	changes = Counter()
	samples = []
	for name in frappe.get_all("Employee Maternity", pluck="name", order_by="name"):
		doc = frappe.get_doc("Employee Maternity", name)
		doc._doc_before_save = frappe.get_doc(doc.as_dict())
		before = {f: doc.get(f) for f in FIELDS}

		if not doc.leave_months and doc.maternity_from_date and doc.maternity_to_date:
			doc.leave_months = _nearest_months(doc.maternity_from_date, doc.maternity_to_date)
		doc.calculate_derived_dates()

		diff = {
			f: (before[f], doc.get(f)) for f in FIELDS
			if str(before[f] or "") != str(doc.get(f) or "")
		}
		if not diff:
			continue
		for f in diff:
			changes[f] += 1
		changes["records"] += 1
		if len(samples) < 12:
			samples.append((name, {k: (str(a), str(b)) for k, (a, b) in diff.items()}))
		if not dry_run:
			frappe.db.set_value(
				"Employee Maternity", name, {f: doc.get(f) for f in diff}, update_modified=False
			)

	prefix = "[DRY-RUN] " if dry_run else ""
	print(f"   {prefix}hồ sơ đổi: {dict(changes)}")
	for s in samples:
		print("     ", s)

	if not dry_run:
		if frappe.db.has_column("Employee Maternity", "maternity_from_date_estimate"):
			assert not frappe.db.count(
				"Employee Maternity", {"maternity_from_date_estimate": ("is", "set")}
			), "maternity_from_date_estimate còn dữ liệu — không drop"
			frappe.db.sql_ddl(
				"ALTER TABLE `tabEmployee Maternity` DROP COLUMN `maternity_from_date_estimate`"
			)
			print("   đã DROP cột maternity_from_date_estimate")
		frappe.db.commit()
		from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity import (
			calculate_all_maternity_statuses,
		)

		print(f"   status: {calculate_all_maternity_statuses()}")
	return dict(changes)
