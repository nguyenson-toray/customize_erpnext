# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Import sổ nghỉ phép của HR (`AL_data.xlsx`) thành Leave Application **draft**.

Kế hoạch + số liệu đã kiểm chứng: `PLAN_IMPORT_AL_2026.md`.
Quy tắc nghiệp vụ: `QUY_DINH_NGHI_PHEP_2025.md`.

Vì sao **draft** (`docstatus = 0`):
  - chưa sinh Attendance (HRMS chỉ chạy `update_attendance()` ở `on_submit`)
  - chưa ghi `Leave Ledger Entry` ⇒ số dư phép không đổi
  - HR rà soát trên UI rồi mới duyệt và submit
`validate()` **vẫn chạy** khi insert, nên các dòng sai (rơi vào ngày nghỉ, ngoài khoảng làm việc)
vẫn bị bắt ngay ở bước này thay vì lúc submit hàng loạt.

`status = "Open"` chứ không phải `"Approved"`:
  - đúng nghĩa "chưa duyệt" của một bản nháp
  - tránh `notify_approval_status()` (`hrms/mixins/pwa_notifications.py:10`) sinh ~6.900 bản
    PWA Notification rác — hàm đó chỉ chạy khi status đổi sang Approved/Rejected và **không**
    bị chặn bởi `HR Settings.send_leave_notification`

Chạy:
    bench --site erp.tiqn.local execute \\
        customize_erpnext.overrides.leave_application.import_leave.run --kwargs "{'dry_run': 1}"
"""

import collections
import os
from datetime import timedelta

import frappe
from frappe.utils import getdate

# Cột (0-based) trong AL_data.xlsx — header 2 dòng, dữ liệu từ dòng 3
COL_STT, COL_EMP, COL_DATE, COL_CODE, COL_NOTE = 0, 1, 30, 31, 33

# Mã "Chấm công" của quy định → abbreviation của Leave Type
CODE_TO_ABBR = {
	"P": "P", "P/2": "P",
	"O": "O", "O/2": "O",
	"CO": "CO", "CO/2": "CO",
	"HL": "HL", "HL/2": "HL",
	"KL": "KL", "NB": "NB", "TS": "TS", "DS": "DS", "HS": "HS", "MC": "MC",
}

DEFAULT_FILE = os.path.join(os.path.dirname(__file__), "AL_data.xlsx")


# ---------------------------------------------------------------------------
# Đọc & phân loại
# ---------------------------------------------------------------------------


def _read(path: str) -> list:
	import openpyxl

	wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
	return [r for r in wb["Sheet1"].iter_rows(min_row=3, values_only=True) if r[COL_EMP]]


def _date(v):
	return v.date() if hasattr(v, "date") else getdate(v) if v else None


def _code(row) -> str:
	return str(row[COL_CODE]).strip() if row[COL_CODE] is not None else ""


def _leave_type_by_abbr() -> dict:
	return {
		r.custom_abbreviation: r.name
		for r in frappe.get_all("Leave Type", fields=["name", "custom_abbreviation"])
		if r.custom_abbreviation
	}


def _holidays() -> set:
	"""Ngày nghỉ của mọi Holiday List đang gán (cấp Company, 0 nhân viên tự đặt riêng)."""
	lists = [
		a.holiday_list
		for a in frappe.get_all("Holiday List Assignment", fields=["holiday_list"])
	]
	return {
		h.holiday_date
		for h in frappe.get_all(
			"Holiday", filters={"parent": ["in", lists or [""]]}, fields=["holiday_date"]
		)
	}


# ---------------------------------------------------------------------------
# Gộp dòng → đơn nghỉ  (Cách C, PLAN_IMPORT_AL_2026.md mục 5)
# ---------------------------------------------------------------------------


def build_applications(rows: list, holidays: set) -> tuple:
	"""Trả về `(danh sách đơn, danh sách dòng bị loại)`.

	Mỗi đơn: `{employee, code, from_date, to_date, half_day, source_rows, stt, notes}`.
	"""
	leave_rows, skipped = [], []
	for r in rows:
		c = _code(r)
		if c in CODE_TO_ABBR:
			leave_rows.append(r)
		else:
			skipped.append((r, "đi trễ/về sớm hoặc mã bất thường: %r" % c))

	groups = collections.defaultdict(list)
	for r in leave_rows:
		groups[(r[COL_STT], r[COL_EMP], _code(r))].append(r)

	apps = []
	for (stt, emp, code), grp in groups.items():
		grp.sort(key=lambda r: _date(r[COL_DATE]))
		notes = [str(r[COL_NOTE]).strip() for r in grp if r[COL_NOTE]]

		if code.endswith("/2"):
			# Nửa ngày: HRMS chỉ cho MỘT half_day_date mỗi đơn ⇒ mỗi dòng một đơn
			for r in grp:
				d = _date(r[COL_DATE])
				apps.append(_app(emp, code, d, d, True, 1, stt, notes))
			continue

		# Trọn ngày: cắt thành đoạn liên tục, được nhảy qua ngày trong Holiday List
		run = [grp[0]]
		for prev, cur in zip(grp, grp[1:]):
			p, c_ = _date(prev[COL_DATE]), _date(cur[COL_DATE])
			gap = [p + timedelta(days=i) for i in range(1, (c_ - p).days)]
			if all(g in holidays for g in gap):
				run.append(cur)
			else:
				apps += _split_if_daycount_mismatch(emp, code, run, holidays, stt, notes)
				run = [cur]
		apps += _split_if_daycount_mismatch(emp, code, run, holidays, stt, notes)

	return apps, skipped


def _app(emp, code, f, t, half, n, stt, notes):
	return {
		"employee": emp, "code": code, "from_date": f, "to_date": t,
		"half_day": half, "source_rows": n, "stt": stt, "notes": notes,
	}


def _split_if_daycount_mismatch(emp, code, run, holidays, stt, notes):
	"""Guard mục 5.2 — chỉ gộp khi HRMS đếm ra ĐÚNG số dòng nguồn.

	`TS` có `include_holiday = 1` (HRMS đếm cả Chủ Nhật) và `DS` thì HR ghi nhiều dòng hơn số
	ngày HRMS đếm. Gộp trong hai ca đó làm sai sổ phép ⇒ tách về 1 đơn / 1 dòng.
	"""
	f, t = _date(run[0][COL_DATE]), _date(run[-1][COL_DATE])
	span = (t - f).days + 1
	include_holiday = frappe.db.get_value("Leave Type", _LT_CACHE[code], "include_holiday")
	hrms_days = span if include_holiday else span - sum(
		1 for i in range(span) if (f + timedelta(days=i)) in holidays
	)
	if abs(hrms_days - len(run)) < 0.001:
		return [_app(emp, code, f, t, False, len(run), stt, notes)]
	return [
		_app(emp, code, _date(r[COL_DATE]), _date(r[COL_DATE]), False, 1, stt, notes)
		for r in run
	]


_LT_CACHE = {}


# ---------------------------------------------------------------------------
# Chạy
# ---------------------------------------------------------------------------


def run(dry_run: int = 1, path: str | None = None, batch_size: int = 200, limit: int = 0):
	"""Import thành Leave Application **draft**. `dry_run=1` chỉ báo cáo, không ghi gì."""
	dry_run, limit = int(dry_run), int(limit)
	path = path or DEFAULT_FILE
	by_abbr = _leave_type_by_abbr()
	global _LT_CACHE
	_LT_CACHE = {c: by_abbr[a] for c, a in CODE_TO_ABBR.items() if a in by_abbr}

	missing = sorted({a for a in CODE_TO_ABBR.values() if a not in by_abbr})
	if missing:
		frappe.throw(f"Thiếu Leave Type cho mã: {missing}")

	rows = _read(path)
	holidays = _holidays()
	apps, skipped = build_applications(rows, holidays)
	apps.sort(key=lambda a: (a["employee"], a["from_date"]))
	if limit:
		apps = apps[:limit]

	print(f"Dòng đọc được          : {len(rows)}")
	print(f"Dòng không phải nghỉ phép: {len(skipped)}")
	print(f"→ Leave Application     : {len(apps)}  "
	      f"({sum(1 for a in apps if a['from_date'] != a['to_date'])} phiếu nhiều ngày, "
	      f"{sum(1 for a in apps if a['half_day'])} nửa ngày)")
	if dry_run:
		print("\n[DRY RUN] không ghi gì. Bỏ `dry_run` để tạo draft.")
		_report_by_code(apps)
		return {"applications": len(apps), "skipped": len(skipped)}

	created = existing = 0
	failures = []
	frappe.flags.mute_messages = True
	for i, a in enumerate(apps, 1):
		# Savepoint cho TỪNG đơn. `frappe.db.rollback()` trần sẽ cuốn theo mọi bản ghi tốt
		# chưa commit trong lô — một dòng lỗi ở giữa lô 200 làm mất 199 dòng đã insert.
		frappe.db.savepoint("import_leave_row")
		try:
			if _already_there(a):
				existing += 1
				continue
			_insert_draft(a)
			created += 1
		except Exception as e:
			failures.append((a["employee"], a["code"], str(a["from_date"]),
			                 str(a["to_date"]), str(e).split("\n")[0][:120]))
			frappe.db.rollback(save_point="import_leave_row")
		if i % batch_size == 0:
			frappe.db.commit()
			print(f"  ... {i}/{len(apps)}  tạo {created}, bỏ qua {existing}, lỗi {len(failures)}")
	frappe.db.commit()
	frappe.flags.mute_messages = False

	print(f"\nTẠO MỚI (draft): {created} | đã có sẵn: {existing} | LỖI: {len(failures)}")
	_report_failures(failures)
	return {"created": created, "existing": existing, "failed": len(failures),
	        "failures": failures}


def _already_there(a) -> bool:
	return bool(frappe.db.exists("Leave Application", {
		"employee": a["employee"],
		"leave_type": _LT_CACHE[a["code"]],
		"from_date": a["from_date"],
		"to_date": a["to_date"],
		"docstatus": ["<", 2],
	}))


def _insert_draft(a):
	doc = frappe.new_doc("Leave Application")
	doc.employee = a["employee"]
	doc.leave_type = _LT_CACHE[a["code"]]
	doc.from_date = a["from_date"]
	doc.to_date = a["to_date"]
	if a["half_day"]:
		doc.half_day = 1
		doc.half_day_date = a["from_date"]
	# "Open" = bản nháp chưa duyệt; cũng để tránh PWA Notification rác (xem docstring module)
	doc.status = "Open"
	desc = [f"[Import AL_data] STT {a['stt']} · mã {a['code']}"]
	if a["notes"]:
		desc.append(" · ".join(dict.fromkeys(a["notes"])))
	doc.description = "\n".join(desc)
	doc.flags.ignore_permissions = True
	doc.insert()


def _report_by_code(apps):
	c = collections.Counter(a["code"] for a in apps)
	print("\nSố phiếu theo mã:")
	for k, v in sorted(c.items(), key=lambda x: -x[1]):
		print(f"   {k:>6} : {v}")


def _report_failures(failures):
	if not failures:
		return
	groups = collections.Counter(f[4][:70] for f in failures)
	print("\nLỗi theo nguyên nhân:")
	for msg, n in groups.most_common():
		print(f"   {n:>4} × {msg}")
	print("\n10 dòng đầu:")
	for f in failures[:10]:
		print(f"   {f[0]} {f[1]:>5} {f[2]}→{f[3]}: {f[4]}")


def submit_imported(batch_size: int = 200, limit: int = 0, to_date: str | None = None):
	"""Duyệt + submit các draft đã import. **Chỉ chạy khi HR đã rà soát xong.**

	🔴 Submit sẽ sinh Attendance và ghi Leave Ledger Entry — không còn quay lại được bằng
	rollback. Sau bước này phải chạy `bulk_update_attendance_optimized` cho toàn khoảng ngày
	để engine và luồng Leave Application đồng thuận.
	"""
	filters = {"docstatus": 0, "description": ["like", "[Import AL_data]%"]}
	if to_date:
		# Lọc theo `to_date` chứ không phải `from_date`: đơn vắt qua mốc sẽ sinh Attendance
		# cho cả những ngày SAU mốc, không nằm trong phạm vi được duyệt.
		filters["to_date"] = ["<=", to_date]
	names = [
		d.name for d in frappe.get_all(
			"Leave Application", filters=filters,
			fields=["name"], order_by="employee, from_date",
			limit_page_length=int(limit) or 0,
		)
	]
	print(f"Draft cần submit{f' (to_date <= {to_date})' if to_date else ''}: {len(names)}")
	done, failures = 0, []
	frappe.flags.mute_messages = True
	for i, name in enumerate(names, 1):
		frappe.db.savepoint("submit_leave_row")
		try:
			doc = frappe.get_doc("Leave Application", name)
			# status đã là "Approved" từ trước; chỉ gán khi cần để `has_value_changed()`
			# không kích hoạt notify_approval_status() -> đẻ PWA Notification rác.
			if doc.status != "Approved":
				doc.status = "Approved"
			doc.flags.ignore_permissions = True
			doc.submit()
			done += 1
		except Exception as e:
			failures.append((name, str(e).split("\n")[0][:120]))
			frappe.db.rollback(save_point="submit_leave_row")
		if i % batch_size == 0:
			frappe.db.commit()
			print(f"  ... {i}/{len(names)} submit {done}, lỗi {len(failures)}")
	frappe.db.commit()
	frappe.flags.mute_messages = False
	print(f"\nSUBMIT: {done} | LỖI: {len(failures)}")
	for f in failures[:10]:
		print("   ", f)
	return {"submitted": done, "failed": len(failures)}


def verify(path: str | None = None):
	"""Đối chiếu số ngày nghỉ ERP (draft) với file HR, theo từng mã. Ngưỡng 0,01 ngày."""
	path = path or DEFAULT_FILE
	rows = _read(path)
	hr = collections.Counter()
	for r in rows:
		c = _code(r)
		if c in CODE_TO_ABBR:
			hr[CODE_TO_ABBR[c]] += 0.5 if c.endswith("/2") else 1

	abbr = {r.name: r.custom_abbreviation for r in frappe.get_all(
		"Leave Type", fields=["name", "custom_abbreviation"])}
	erp = collections.Counter()
	imported = {"description": ("like", "[Import AL_data]%")}
	for la in frappe.get_all("Leave Application", filters=imported,
	                         fields=["leave_type", "total_leave_days"]):
		erp[abbr.get(la.leave_type)] += la.total_leave_days

	print("Leave Application từ import:", frappe.db.count("Leave Application", imported))
	for st in (0, 1, 2):
		print(f"   docstatus={st}: {frappe.db.count('Leave Application', {**imported, 'docstatus': st})}")

	print(f"\n{'mã':6}{'HR (ngày)':>12}{'ERP':>12}{'lệch':>9}")
	diffs = []
	for k in sorted(set(hr) | set(erp)):
		h, e = hr[k], erp[k]
		flag = ""
		if abs(h - e) > 0.01:
			diffs.append((k, h, e))
			flag = "  ← LỆCH"
		print(f"{k:6}{h:>12.1f}{e:>12.1f}{e - h:>9.1f}{flag}")
	print(f"{'TỔNG':6}{sum(hr.values()):>12.1f}{sum(erp.values()):>12.1f}"
	      f"{sum(erp.values()) - sum(hr.values()):>9.1f}")
	return diffs
