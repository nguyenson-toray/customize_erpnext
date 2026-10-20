# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Chuyển `AL_HR.xlsx` (sổ nghỉ HR đang dùng) sang đúng định dạng `AL_data_2026.xlsx` để
`import_leave_application.run(path=...)` đọc được nguyên trạng.

    bench --site erp.tiqn.local execute \\
        customize_erpnext.overrides.leave_application.convert_al_hr.convert \\
        --kwargs "{'since': '2026-09-25'}"

===============================================================================
FILE NGUỒN — mỗi dòng là MỘT NGÀY nghỉ của một nhân viên
===============================================================================

`Sheet1`, 3 dòng tiêu đề (nhóm / nhóm con / số thứ tự cột), dữ liệu từ dòng 4. Chỉ đọc:

    A  STT        số phiếu, thành tiền tố của Reason
    B  Mã NV      C  Họ và tên
    AE Ngày       AF Chấm công (mã nghỉ)       AH Ghi chú

Các cột nhóm G..AC chỉ lặp lại mã chấm công dưới dạng 1 / 0,5 — không đọc.

===============================================================================
QUY TẮC — suy ngược từ `AL_data_2026.xlsx`, khớp 7.483/7.483 dòng (đo 20/10/2026)
===============================================================================

1. Mã chấm công là **số** = đi trễ / về sớm (tỷ lệ công), không phải đơn nghỉ → bỏ.
   Dòng không có mã NV (`#N/A`) → bỏ.
2. `X/2` → Abbreviation `X` + `Half Day = True`.
3. Gom theo `(STT, NV, mã, nửa ngày, ghi chú)`.
4. `Leave Type Name` tra từ sheet `Leave Type`. `COP` / `OP` (nửa con ốm/ốm + nửa phép năm)
   không có trong bảng → để trống, importer bỏ qua và liệt kê để HR nhập tay 2 đơn nửa ngày.
5. `Reason = "<STT> - <ghi chú>"`.

⚠ **Khác bản 05/09 ở bước 3** — bản cũ lấy `min..max` ngày của nhóm, nên khi một STT có
khoảng trống thì đơn **nuốt luôn ngày làm việc không có trong file** (TIQN-1076 nghỉ 18/09 và
25/09 → một đơn 18→25/09, trừ 6 ngày thay vì 2). Bản này chỉ nối hai ngày khi **mọi ngày ở
giữa là Chủ Nhật hoặc ngày lễ**. Đơn nửa ngày không bao giờ nối: HRMS chỉ trừ nửa ngày cho
`half_day_date`, các ngày còn lại của đơn bị tính trọn.

30 đơn đã submit trước 25/08 tạo theo quy tắc cũ — cố ý giữ nguyên, xem sheet `Review`
khi chạy với `since=None`.

===============================================================================
FILE ĐÍCH
===============================================================================

- `Data`        8 cột giống hệt `AL_data_2026.xlsx` — importer đọc sheet này.
- `Leave Type`  chép từ `AL_data_2026.xlsx` — importer tra mã viết tắt ở đây.
- `Review`      dòng bị bỏ, đơn bị tách vì khoảng trống, đơn trùng ngày. Importer không đọc.

🔴 File chứa họ tên nhân viên — không commit.
"""

import collections
import datetime
import os

import frappe
from frappe.utils import getdate, nowdate

HERE = os.path.dirname(__file__)
DEFAULT_SRC = os.path.join(HERE, "AL_HR.xlsx")
TEMPLATE = os.path.join(HERE, "AL_data_2026.xlsx")

COL_STT, COL_EMP, COL_NAME, COL_DATE, COL_CODE, COL_NOTE = 0, 1, 2, 30, 31, 33
FIRST_DATA_ROW = 4

HEADER = ["Employee", "Employee Name", "Abbreviation", "Half Day", "From Date", "To Date",
          "Leave Type Name", "Reason"]


def convert(src: str | None = None, dst: str | None = None, since: str | None = "2026-09-25"):
	"""Đọc `src`, ghi `dst`. `since`: chỉ giữ đơn có `from_date > since` (mốc của lần import
	trước); `None` = cả file."""
	import openpyxl

	src = src or DEFAULT_SRC
	dst = dst or os.path.join(HERE, f"AL_data_{nowdate().replace('-', '')}.xlsx")
	since = getdate(since) if since else None

	wb = openpyxl.load_workbook(src, data_only=True, read_only=True)
	rows = list(wb[wb.sheetnames[0]].iter_rows(min_row=FIRST_DATA_ROW, values_only=True))
	abbr_map = _template_leave_types()

	groups, names, review = collections.defaultdict(set), {}, []
	for row_no, r in enumerate(rows, start=FIRST_DATA_ROW):
		emp = str(r[COL_EMP]).strip() if r[COL_EMP] else ""
		date = r[COL_DATE]
		if not emp or not isinstance(date, datetime.datetime):
			if any(c not in (None, "", " ", 0) for c in r[:COL_NOTE + 1]):
				review.append(("Không có mã NV / ngày", row_no, emp, r[COL_STT], None, None, r[COL_CODE], r[COL_NOTE]))
			continue
		date = date.date()
		code = r[COL_CODE]
		if not isinstance(code, str) or not code.strip():
			# Số = tỷ lệ công của ngày đi trễ / về sớm, không phải đơn nghỉ.
			if not since or date > since:
				review.append(("Đi trễ / về sớm — không phải đơn nghỉ", row_no, emp, r[COL_STT], date, date, code, r[COL_NOTE]))
			continue
		code = code.strip().upper()
		half = code.endswith("/2")
		abbr = code[:-2] if half else code
		note = str(r[COL_NOTE]).strip() if r[COL_NOTE] else ""
		groups[(r[COL_STT], emp, abbr, half, note)].add(date)
		names[emp] = r[COL_NAME]

	off_days = _off_days()
	apps = []
	for (stt, emp, abbr, half, note), dates in groups.items():
		runs = _runs(sorted(dates), off_days, half)
		for f, t in runs:
			if since and f <= since:
				continue
			apps.append({
				"employee": emp, "employee_name": names[emp], "abbr": abbr, "half_day": half,
				"from_date": f, "to_date": t, "leave_type": abbr_map.get(abbr, ""),
				"reason": f"{stt} - {note}" if note else str(stt),
			})
		if len(runs) > 1 and not half and (not since or runs[-1][1] > since):
			review.append(("Tách đơn vì khoảng trống có ngày làm việc", None, emp, stt, runs[0][0], runs[-1][1], abbr,
			               " · ".join(f"{a:%d/%m}→{b:%d/%m}" for a, b in runs)))

	apps.sort(key=lambda a: (a["from_date"], a["employee"]))
	for a in apps:
		if not a["leave_type"]:
			review.append(("Mã không có Leave Type — HR nhập tay", None, a["employee"], a["reason"].split(" - ")[0],
			               a["from_date"], a["to_date"], f"{a['abbr']}/2" if a["half_day"] else a["abbr"], a["reason"]))
	review += _overlaps(apps)

	_write(dst, apps, review)

	kinds = collections.Counter(r[0] for r in review)
	print(f"Nguồn            : {src}  ({len(rows)} dòng)")
	print(f"Mốc              : from_date > {since}" if since else "Mốc              : cả file")
	print(f"→ Đơn            : {len(apps)}  ({sum(1 for a in apps if a['from_date'] != a['to_date'])} nhiều ngày, "
	      f"{sum(1 for a in apps if a['half_day'])} nửa ngày, "
	      f"{sum(1 for a in apps if a['to_date'] > getdate())} có ngày sau hôm nay)")
	for (abbr, half), n in collections.Counter((a["abbr"], a["half_day"]) for a in apps).most_common():
		print(f"      {n:>6}  {abbr}{'/2' if half else ''}")
	print("Review           :")
	for k, n in kinds.most_common():
		print(f"      {n:>6}  {k}")
	print(f"Ghi              : {dst}")
	return {"applications": len(apps), "review": dict(kinds), "path": dst}


def _runs(dates, off_days, half):
	"""Tách danh sách ngày thành các đoạn liền. Hai ngày được nối khi mọi ngày ở giữa là
	Chủ Nhật / ngày lễ. Nửa ngày: mỗi ngày một đơn."""
	if half:
		return [(d, d) for d in dates]
	runs, start, prev = [], dates[0], dates[0]
	for d in dates[1:]:
		between = (prev + datetime.timedelta(days=i) for i in range(1, (d - prev).days))
		if all(x.weekday() == 6 or x in off_days for x in between):
			prev = d
			continue
		runs.append((start, prev))
		start = prev = d
	runs.append((start, prev))
	return runs


def _off_days() -> set:
	"""Ngày lễ (không tính nghỉ tuần — Chủ Nhật đã xét riêng) của mọi Holiday List.

	Công ty đặt một Holiday List mỗi năm (`2025`, `2026`, `2027`), không có list riêng
	theo nhân viên, nên gộp tất cả là đủ."""
	return {getdate(d) for d in frappe.get_all("Holiday", filters={"weekly_off": 0}, pluck="holiday_date")}


def _template_leave_types() -> dict:
	"""`{mã: tên Leave Type}` từ sheet `Leave Type` của `AL_data_2026.xlsx`."""
	import openpyxl

	wb = openpyxl.load_workbook(TEMPLATE, data_only=True, read_only=True)
	return {
		str(r[1]).strip(): str(r[0]).strip()
		for r in wb["Leave Type"].iter_rows(min_row=2, values_only=True)
		if r and r[0] and r[1]
	}


def _overlaps(apps) -> list:
	"""Hai đơn cùng NV chồng ngày → HRMS chặn đơn thứ hai. Ngoại lệ: hai đơn NỬA ngày cùng
	ngày là hợp lệ (override `custom_create_or_update_attendance` hỗ trợ dual leave)."""
	out = []
	by_emp = collections.defaultdict(list)
	for a in apps:
		by_emp[a["employee"]].append(a)
	for emp, items in by_emp.items():
		items.sort(key=lambda a: a["from_date"])
		for i, a in enumerate(items):
			for b in items[i + 1:]:
				if b["from_date"] > a["to_date"]:
					break
				if a["half_day"] and b["half_day"]:
					continue
				out.append(("Trùng ngày — HRMS sẽ chặn đơn sau", None, emp, None, b["from_date"],
				            min(a["to_date"], b["to_date"]),
				            f"{a['abbr']}{'/2' if a['half_day'] else ''} + {b['abbr']}{'/2' if b['half_day'] else ''}",
				            f"{a['reason']}  |  {b['reason']}"))
	return out


def _write(dst, apps, review):
	import openpyxl

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "Data"
	ws.append(HEADER)
	for a in apps:
		ws.append([
			a["employee"], a["employee_name"], a["abbr"], True if a["half_day"] else None,
			_dt(a["from_date"]), _dt(a["to_date"]), a["leave_type"] or None, a["reason"],
		])
	_date_format(ws, ("E", "F"))

	lt = wb.create_sheet("Leave Type")
	lt.append(["Leave Type Name", "Abbreviation"])
	for abbr, name in _template_leave_types().items():
		lt.append([name, abbr])

	rv = wb.create_sheet("Review")
	rv.append(["Loại", "Dòng AL_HR", "Employee", "STT", "From Date", "To Date", "Mã", "Chi tiết"])
	for r in review:
		rv.append([r[0], r[1], r[2], r[3], _dt(r[4]), _dt(r[5]), r[6], r[7]])
	_date_format(rv, ("E", "F"))

	wb.save(dst)


def _dt(d):
	return datetime.datetime.combine(d, datetime.time()) if isinstance(d, datetime.date) else d


def _date_format(ws, cols):
	for col in cols:
		ws.column_dimensions[col].width = 12
		for cell in ws[col][1:]:
			cell.number_format = "DD/MM/YYYY"
