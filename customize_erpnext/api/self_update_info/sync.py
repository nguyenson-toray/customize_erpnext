"""Review + Sync phiếu vào Employee.

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from .rules import (
	INFO_DT,
)
from .config import (
	_build_config,
	_get_setting,
	_is_table,
)
from .values import (
	_table_list,
)
from .access import (
	_require_hr,
)


# Address groups on Employee whose "_full" is rebuilt = village, commune, province.
_ADDRESS_GROUPS = [
	{
		"province": "custom_current_address_province",
		"commune": "custom_current_address_commune",
		"village": "custom_current_address_village",
		"full": "custom_current_address_full",
	},
	{
		"province": "custom_permanent_address_province",
		"commune": "custom_permanent_address_commune",
		"village": "custom_permanent_address_village",
		"full": "custom_permanent_address_full",
	},
	# 🚧 TẠM TẮT 21/08/2026 — field custom_place_of_origin_address_* đã bị gỡ khỏi Employee.
	#    Giữ nguyên để khai lại sau; bỏ comment cả khối là chạy như cũ.
	# {
	# "province": "custom_place_of_origin_address_province",
	# "commune": "custom_place_of_origin_address_commune",
	# "village": "custom_place_of_origin_address_village",
	# "full": "custom_place_of_origin_address_full",
	# },
]


def _coerce_for_employee(value, fieldtype):
	"""Convert a submitted (string) value to something safe for emp.set()."""
	if value is None:
		return None
	sval = str(value).strip()
	if sval == "":
		# Empty → clear numeric/date/link fields; keep "" for text.
		if fieldtype in ("Int", "Float", "Currency", "Date", "Datetime", "Time", "Link"):
			return None
		return ""
	if fieldtype == "Check":
		return 1 if sval in ("1", "true", "True", "on", "yes", "Có") else 0
	if fieldtype == "Int":
		return int(float(sval))
	if fieldtype in ("Float", "Currency"):
		return float(sval)
	return sval


def _row_key(f, row):
	"""Nội dung 1 dòng theo các cột cấu hình (None / "" / 0 coi như trống) để so dòng phiếu với dòng Employee."""
	return tuple(
		"" if row.get(c["fieldname"]) in (None, "", 0) else str(row.get(c["fieldname"])).strip() for c in f["columns"]
	)


def _sync_table_rows(emp, f, rows):
	"""Ghi bảng con của phiếu vào Employee, trả (pairs, số dòng Employee giữ nguyên, số dòng Employee xoá).

	- dòng có `name` của Employee → sửa đúng các cột cấu hình (cột khác giữ nguyên);
	- dòng không `name` mà giống hệt một dòng Employee chưa ghép → coi là dòng đó. Phiếu Sync lại
	  (HR đưa về Submitted) từng thêm bản sao mỗi lần: TIQN-2547 có 3 dòng học vấn giống nhau (22/10/2026);
	- còn lại → thêm mới.
	Dòng Employee không có trong phiếu → giữ, miễn tổng số dòng không vượt Max Rows (giữ dòng mới nhất);
	phần dư bị XOÁ (user 23/10/2026: Học vấn / Kinh nghiệm chỉ 1 dòng, theo lần cập nhật cuối).
	Phiếu cũ nhiều dòng hơn Max Rows → chỉ lấy `max_rows` dòng cuối.
	`pairs` = [(dòng phiếu, dòng Employee)] để sau emp.save() ghi `name` ngược vào phiếu."""
	rows = _table_list(rows)
	if f.get("max_rows"):
		rows = rows[-f["max_rows"]:]
	existing = {r.name: r for r in emp.get(f["fieldname"]) or []}
	seen = set()
	vals = [{c["fieldname"]: _coerce_for_employee(r.get(c["fieldname"]), c["fieldtype"]) for c in f["columns"]} for r in rows]
	children = [None] * len(rows)
	# Dòng có `name` ghép trước, để dòng không `name` không giành mất dòng Employee của chúng.
	for i, r in enumerate(rows):
		child = existing.get(r.get("name"))
		if child is not None and child.name not in seen:
			children[i] = child
			seen.add(child.name)
	for i in range(len(rows)):
		if children[i] is None:
			key = _row_key(f, vals[i])
			child = next((c for n, c in existing.items() if n not in seen and _row_key(f, c) == key), None)
			if child is not None:
				children[i] = child
				seen.add(child.name)
	# Dòng Employee ngoài phiếu: giữ các dòng cuối (mới nhất) vừa chỗ trống còn lại, xoá trước khi thêm dòng mới.
	others = [c for c in emp.get(f["fieldname"]) or [] if c.name not in seen]
	room = max(f["max_rows"] - len(rows), 0) if f.get("max_rows") else len(others)
	drop = others[:len(others) - room]
	for c in drop:
		emp.remove(c)
	for i in range(len(rows)):
		if children[i] is None:
			children[i] = emp.append(f["fieldname"], vals[i])
		else:
			children[i].update(vals[i])
	return list(zip(rows, children)), len(others) - len(drop), len(drop)


def _rows_with_names(pairs):
	"""Dòng phiếu kèm `name` dòng Employee đã ghép/tạo (gọi sau emp.save, dòng mới mới có name)."""
	return [{"name": child.name, **{k: v for k, v in r.items() if k != "name"}} for r, child in pairs]


def _rebuild_address_full(emp, changed_fieldnames):
	"""Recompute custom_*_address_full = village + commune + province (like the
	Employee form) for any address group whose parts were touched."""
	for g in _ADDRESS_GROUPS:
		if not any(g[k] in changed_fieldnames for k in ("province", "commune", "village")):
			continue
		parts = [emp.get(g["village"]), emp.get(g["commune"]), emp.get(g["province"])]
		emp.set(g["full"], ", ".join([p for p in parts if p]))


@frappe.whitelist()
def review_forms(names):
	"""Mark Submitted forms as Reviewed (required before syncing).

	`names` = JSON list of Employee Self Update Info names.
	Returns {reviewed, skipped, results:[{employee, ok, message}]}.
	"""
	_require_hr()
	if isinstance(names, str):
		names = json.loads(names or "[]")
	if not names:
		frappe.throw(_("No records selected."))

	reviewed, skipped, results = 0, 0, []
	for name in names:
		doc = frappe.get_doc(INFO_DT, name)
		if doc.status != "Submitted":
			skipped += 1
			results.append({"employee": doc.employee, "ok": False,
				"message": _("Bỏ qua — trạng thái {0} (chỉ review được bản Submitted)").format(doc.status)})
			continue
		doc.status = "Reviewed"
		doc.reviewed_on = now_datetime()
		doc.reviewed_by = frappe.session.user
		doc.save(ignore_permissions=True)
		reviewed += 1
		results.append({"employee": doc.employee, "ok": True, "message": _("Đã review")})
	frappe.db.commit()
	return {"reviewed": reviewed, "skipped": skipped, "results": results}


@frappe.whitelist()
def get_syncable_fields():
	"""Return the real Employee fields (non-custom) that Sync can write, for the
	HR field-picker dialog. `[{fieldname, label}]`."""
	_require_hr()
	config = _build_config()
	return [
		{"fieldname": f["fieldname"], "label": f["label"]}
		for sec in config["sections"]
		for f in sec["fields"]
		if not f.get("custom") and f["fieldname"] not in ("employee", "name")
	]


@frappe.whitelist()
def sync_to_employee(names, fields=None):
	"""Write submissions into the Employee record.

	Only fields that exist on Employee (incl. custom_ fields) are written; custom
	free-form fields and remarks are ignored. `fields` (optional JSON list of
	fieldnames) limits Sync to the HR-selected fields; omitted → all configured
	fields. When Disable Review is on, records are synced straight from Submitted;
	otherwise only Reviewed records are synced. Each record is saved independently
	so one failure does not block the rest. Returns {synced, failed, skipped, results}.
	"""
	_require_hr()
	if isinstance(names, str):
		names = json.loads(names or "[]")
	if not names:
		frappe.throw(_("No records selected."))
	if isinstance(fields, str):
		fields = json.loads(fields or "null")
	if fields is not None and not fields:
		frappe.throw(_("Select at least one field to sync."))

	setting = _get_setting()
	# Disable Review → sync from Submitted; else require Reviewed. Reviewed is
	# always accepted so legacy already-reviewed records still sync.
	allowed = {"Submitted", "Reviewed"} if setting.get("disable_review") else {"Reviewed"}

	config = _build_config()
	# Real Employee fields only (non-custom, excluding identity fields).
	emp_fields = {
		f["fieldname"]: f
		for sec in config["sections"]
		for f in sec["fields"]
		if not f.get("custom") and f["fieldname"] not in ("employee", "name")
	}
	# Limit to the HR-selected fields when provided.
	if fields is not None:
		sel = set(fields)
		emp_fields = {fn: f for fn, f in emp_fields.items() if fn in sel}

	synced, failed, skipped, results = 0, 0, 0, []
	for name in names:
		doc = frappe.get_doc(INFO_DT, name)
		if doc.status not in allowed:
			skipped += 1
			need = _("Submitted") if setting.get("disable_review") else _("Reviewed")
			results.append({"employee": doc.employee, "employee_name": doc.employee_name, "ok": False,
				"message": _("Bỏ qua — cần trạng thái {0} để Sync (hiện tại: {1})").format(need, doc.status)})
			continue

		saved = json.loads(doc.data_json or "{}")
		try:
			emp = frappe.get_doc("Employee", doc.employee)
			meta = emp.meta
			changed = []
			kept_rows = dropped_rows = 0
			table_pairs = []
			for fn, f in emp_fields.items():
				if fn not in saved:
					continue
				if not meta.has_field(fn):
					continue  # field no longer on Employee
				if _is_table(f):
					pairs, kept, dropped = _sync_table_rows(emp, f, saved.get(fn))
					kept_rows += kept
					dropped_rows += dropped
					if isinstance(saved.get(fn), list):
						table_pairs.append((fn, pairs))
					changed.append(fn)
					continue
				emp.set(fn, _coerce_for_employee(saved.get(fn), f["fieldtype"]))
				changed.append(fn)
			_rebuild_address_full(emp, set(changed))
			emp.save(ignore_permissions=True)

			doc.status = "Synced"
			doc.synced_on = now_datetime()
			doc.synced_by = frappe.session.user
			doc.save(ignore_permissions=True)
			if table_pairs:
				# Ghi `name` dòng Employee (dòng mới chỉ có sau emp.save) vào phiếu → lần Sync sau sửa đúng
				# dòng đó. db_set: không qua validate_desk_edit (đây không phải HR sửa nội dung phiếu).
				for fn, pairs in table_pairs:
					saved[fn] = _rows_with_names(pairs)
				doc.db_set("data_json", json.dumps(saved, ensure_ascii=False), update_modified=False)
			frappe.db.commit()
			synced += 1
			msg = _("Đã đồng bộ {0} trường").format(len(changed))
			if kept_rows:
				msg += " · " + _("{0} dòng bảng con không có trong phiếu — giữ nguyên trên Employee").format(kept_rows)
			if dropped_rows:
				msg += " · " + _("{0} dòng bảng con cũ vượt Max Rows — đã xoá khỏi Employee").format(dropped_rows)
			results.append({"employee": doc.employee, "employee_name": doc.employee_name, "ok": True,
				"message": msg})
		except Exception as e:
			frappe.db.rollback()
			failed += 1
			results.append({"employee": doc.employee, "employee_name": doc.employee_name, "ok": False,
				"message": str(e)})
	return {"synced": synced, "failed": failed, "skipped": skipped, "results": results}
