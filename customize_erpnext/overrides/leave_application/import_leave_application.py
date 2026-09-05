# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Import `AL_data_2026.xlsx` thành Leave Application, và dọn sạch dữ liệu cũ trước đó.

Khác `import_leave.py` (bản cũ, đọc `AL_data.xlsx`): file mới **mỗi dòng là một đơn nghỉ
hoàn chỉnh**, HR đã gộp ngày và điền sẵn đúng tên Leave Type. Không còn phải suy ra đơn
từ các dòng chấm công rời rạc, nên bỏ được toàn bộ phần gom đoạn / nhảy qua ngày lễ /
tách khi lệch số ngày của bản cũ.

    Cột (0-based):  0 Employee · 1 Employee Name · 2 Abbreviation · 3 Half Day
                    4 From Date · 5 To Date · 6 Leave Type Name · 7 Reason

===============================================================================
QUY TRÌNH 4 BƯỚC
===============================================================================

    B0  purge()             XOÁ sạch Leave Application + ledger + link  🔴 MỘT CHIỀU
    B1  run(dry_run=1)      đọc file, báo cáo, KHÔNG ghi gì             an toàn
    B2  run(dry_run=0)      tạo Leave Application draft                 xoá lại được
    B3  verify()            đối chiếu số đơn theo loại nghỉ             chỉ đọc
    B4  submit_imported()   submit → sinh Attendance + ghi sổ phép      🔴 MỘT CHIỀU

Sau B4 **bắt buộc** chạy lại engine tính công cho toàn khoảng ngày:

    bench --site erp.tiqn.local console
    from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized
    bulk_update_attendance_optimized("2025-12-26", "<hôm nay>", force_sync=1)

Lý do: submit sinh Attendance qua luồng Leave Application, còn engine tính công là luồng
ghi độc lập thứ hai vào cùng các field đó và luôn ghi sau cùng.

===============================================================================
🔴 `purge()` — hai chỗ dễ làm hỏng số dư phép
===============================================================================

1. **Leave Ledger Entry có HAI chiều.** Chiều CỘNG (`transaction_type = "Leave Allocation"`,
   1.038 dòng / +7.369,92 ngày) là phép được cấp; chiều TRỪ (`"Leave Application"`) là phép
   đã nghỉ. `purge()` **chỉ xoá chiều TRỪ**. Xoá cả bảng là số dư phép của toàn công ty về 0
   trong im lặng, mà Leave Allocation vẫn còn nguyên nên nhìn qua tưởng không sao.

2. **Attendance chỉ GỠ LINK, không xoá.** Bản ghi chấm công là dữ liệu thật từ máy quẹt thẻ,
   không phải hệ quả của đơn nghỉ. Gỡ 5 field liên kết rồi để engine tính lại ở bước cuối.

===============================================================================
DÒNG BỊ LOẠI — cố ý, không phải lỗi
===============================================================================

- **Thiếu `Leave Type Name` và mã viết tắt không tra được.** Đo file 05/09/2026: đúng 1 dòng,
  `TIQN-2070` ngày 24/08 mã `COP` (nửa ngày con ốm + nửa ngày phép năm). HRMS **không** biểu
  diễn được hai loại nghỉ trong một đơn, và bảng `Leave Type` của file cũng không có mã này.
  Cố ý bỏ qua và báo ra để HR tự nhập tay hai đơn nửa ngày.
- **Nhân viên không tồn tại** hoặc **Leave Type không tồn tại** trong ERP.

⚠ `Half Day = True` mà đơn NHIỀU ngày: HRMS bắt buộc có `half_day_date`, nhưng file không nói
nửa ngày rơi vào ngày nào. Mặc định lấy `from_date` và **liệt kê ra** để HR kiểm. Đo file
05/09/2026: 3 đơn (TIQN-1554, TIQN-1021, TIQN-2085). Lệch tối đa 0,5 ngày mỗi đơn.

===============================================================================
CHẠY LẠI CÓ AN TOÀN KHÔNG? — CÓ
===============================================================================

`_already_there()` bỏ qua đơn đã tồn tại theo khoá `(employee, leave_type, from_date,
to_date, docstatus < 2)`, nên chạy lại `run()` trên cả file chỉ tạo phần còn thiếu.
Mỗi đơn có savepoint riêng — một dòng lỗi không cuốn theo cả lô.

Xoá lại các draft đã tạo (chỉ khi CHƯA submit):

    [frappe.delete_doc("Leave Application", n, force=1) for n in frappe.get_all("Leave Application", {"docstatus": 0}, pluck="name")]; frappe.db.commit()
"""

import collections
import os

import frappe
from frappe.utils import getdate

# 🔴 KHÔNG đánh dấu gì vào `description` — đó là nội dung HR đọc, phải đúng cột Reason.
# Hệ quả: B3/B4 nhận diện đơn đã import bằng `docstatus = 0` chứ không bằng marker. Chỉ
# đúng khi đã chạy `purge()` trước (xoá sạch mọi Leave Application). Nếu import mà KHÔNG
# purge thì `submit_imported()` sẽ ôm luôn draft do người khác tạo tay — kiểm số lượng nó
# in ra trước khi để nó chạy.
DEFAULT_FILE = os.path.join(os.path.dirname(__file__), "AL_data_2026.xlsx")

COL_EMP, COL_NAME, COL_ABBR, COL_HALF, COL_FROM, COL_TO, COL_TYPE, COL_REASON = range(8)

# 5 field liên kết đơn nghỉ trên Attendance. Engine ghi lại tất cả ở lần bulk update sau,
# nên chỉ cần gỡ, không cần dựng lại bằng tay.
ATTENDANCE_LEAVE_FIELDS = (
	"leave_type",
	"leave_application",
	"custom_leave_type_2",
	"custom_leave_application_2",
	"custom_leave_application_abbreviation",
)


# ---------------------------------------------------------------------------
# B0 — dọn dữ liệu cũ
# ---------------------------------------------------------------------------


def purge(confirm: int = 0):
	"""XOÁ toàn bộ Leave Application + ledger chiều TRỪ + gỡ link trên Attendance.

	🔴 MỘT CHIỀU. Phải truyền `confirm=1` — đây là thao tác xoá hàng nghìn bản ghi, không
	để lỡ tay chạy được.
	"""
	if not int(confirm):
		frappe.throw("purge() xoá toàn bộ Leave Application. Truyền confirm=1 nếu chắc chắn.")

	before = {
		"leave_application": frappe.db.count("Leave Application"),
		"ledger_leave": frappe.db.count("Leave Ledger Entry", {"transaction_type": "Leave Application"}),
		"ledger_allocation": frappe.db.count("Leave Ledger Entry", {"transaction_type": "Leave Allocation"}),
		"attendance_linked": frappe.db.sql(
			"SELECT COUNT(*) FROM `tabAttendance` WHERE leave_application IS NOT NULL"
			" OR leave_type IS NOT NULL")[0][0],
	}
	print("TRƯỚC KHI XOÁ:", before)

	# Chỉ chiều TRỪ. Chiều CỘNG là phép được cấp — xoá là số dư toàn công ty về 0.
	frappe.db.sql("DELETE FROM `tabLeave Ledger Entry` WHERE transaction_type = 'Leave Application'")

	# Version/Comment mồ côi của đơn nghỉ
	frappe.db.sql("DELETE FROM `tabVersion` WHERE ref_doctype = 'Leave Application'")
	frappe.db.sql("DELETE FROM `tabComment` WHERE reference_doctype = 'Leave Application'")
	frappe.db.sql("DELETE FROM `tabToDo` WHERE reference_type = 'Leave Application'")

	# `docstatus = 1` không xoá được bằng ORM; đây là reset có chủ đích nên đi thẳng SQL.
	frappe.db.sql("DELETE FROM `tabLeave Application`")

	# Attendance: CHỈ gỡ link, giữ nguyên bản ghi (dữ liệu thật từ máy chấm công).
	sets = ", ".join(f"`{f}` = NULL" for f in ATTENDANCE_LEAVE_FIELDS)
	frappe.db.sql(f"UPDATE `tabAttendance` SET {sets} WHERE leave_application IS NOT NULL OR leave_type IS NOT NULL")

	frappe.db.commit()

	after = {
		"leave_application": frappe.db.count("Leave Application"),
		"ledger_leave": frappe.db.count("Leave Ledger Entry", {"transaction_type": "Leave Application"}),
		"ledger_allocation": frappe.db.count("Leave Ledger Entry", {"transaction_type": "Leave Allocation"}),
		"attendance_linked": frappe.db.sql(
			"SELECT COUNT(*) FROM `tabAttendance` WHERE leave_application IS NOT NULL"
			" OR leave_type IS NOT NULL")[0][0],
	}
	print("SAU KHI XOÁ  :", after)

	if after["ledger_allocation"] != before["ledger_allocation"]:
		frappe.throw(
			f"purge() đã đụng vào ledger chiều CỘNG: {before['ledger_allocation']} → "
			f"{after['ledger_allocation']}. Số dư phép hỏng, khôi phục DB ngay."
		)
	return {"before": before, "after": after}


# ---------------------------------------------------------------------------
# Đọc file
# ---------------------------------------------------------------------------


def _read(path: str) -> list:
	import openpyxl

	wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
	# Sheet "Data" là dữ liệu; sheet "Leave Type" là bảng tra mã → tên loại nghỉ.
	ws = wb["Data"] if "Data" in wb.sheetnames else wb[wb.sheetnames[0]]
	return [r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[COL_EMP]]


def _abbr_map(path: str) -> dict:
	"""`{mã viết tắt: tên Leave Type}` lấy từ sheet "Leave Type" của chính file."""
	import openpyxl

	wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
	if "Leave Type" not in wb.sheetnames:
		return {}
	out = {}
	for row in wb["Leave Type"].iter_rows(min_row=2, values_only=True):
		if row and row[0] and row[1]:
			out[str(row[1]).strip()] = str(row[0]).strip()
	return out


def _date(v):
	return getdate(v) if v else None


def build_applications(rows, abbr_map):
	"""`(danh sách đơn, danh sách dòng bị loại, danh sách cảnh báo)`."""
	apps, skipped, warnings = [], [], []

	valid_types = set(frappe.get_all("Leave Type", pluck="name"))
	seen_employees = {}

	for idx, r in enumerate(rows, start=2):  # dòng 1 là tiêu đề
		emp = str(r[COL_EMP]).strip()
		abbr = (str(r[COL_ABBR]).strip() if r[COL_ABBR] else "")
		leave_type = (str(r[COL_TYPE]).strip() if r[COL_TYPE] else "") or abbr_map.get(abbr, "")

		if not leave_type:
			skipped.append((idx, emp, f"không tra được Leave Type (mã {abbr!r})"))
			continue
		if leave_type not in valid_types:
			skipped.append((idx, emp, f"Leave Type không tồn tại trong ERP: {leave_type!r}"))
			continue

		if emp not in seen_employees:
			seen_employees[emp] = frappe.db.exists("Employee", emp)
		if not seen_employees[emp]:
			skipped.append((idx, emp, "nhân viên không tồn tại"))
			continue

		f, t = _date(r[COL_FROM]), _date(r[COL_TO])
		if not f or not t:
			skipped.append((idx, emp, "thiếu From Date / To Date"))
			continue
		if t < f:
			skipped.append((idx, emp, f"To Date {t} < From Date {f}"))
			continue

		half = bool(r[COL_HALF])
		if half and f != t:
			# File không nói nửa ngày rơi vào ngày nào — lấy from_date và báo ra.
			warnings.append((idx, emp, abbr, f"nửa ngày trên đơn nhiều ngày {f} → {t}, lấy half_day_date = {f}"))

		apps.append({
			"row": idx,
			"employee": emp,
			"abbr": abbr,
			"leave_type": leave_type,
			"from_date": f,
			"to_date": t,
			"half_day": half,
			"reason": (str(r[COL_REASON]).strip() if r[COL_REASON] else ""),
		})

	return apps, skipped, warnings


# ---------------------------------------------------------------------------
# B1/B2 — tạo draft
# ---------------------------------------------------------------------------


def run(dry_run: int = 1, path: str | None = None, batch_size: int = 200, limit: int = 0):
	"""Import thành Leave Application **draft**. `dry_run=1` chỉ báo cáo, không ghi gì."""
	dry_run, limit = int(dry_run), int(limit)
	path = path or DEFAULT_FILE

	rows = _read(path)
	apps, skipped, warnings = build_applications(rows, _abbr_map(path))
	apps.sort(key=lambda a: (a["employee"], a["from_date"]))
	if limit:
		apps = apps[:limit]

	print(f"Dòng đọc được       : {len(rows)}")
	print(f"Dòng bị loại        : {len(skipped)}")
	for row_no, emp, why in skipped:
		print(f"      dòng {row_no} · {emp} · {why}")
	print(f"Cảnh báo            : {len(warnings)}")
	for row_no, emp, abbr, why in warnings:
		print(f"      dòng {row_no} · {emp} · {abbr} · {why}")
	print(f"→ Leave Application : {len(apps)}  "
	      f"({sum(1 for a in apps if a['from_date'] != a['to_date'])} phiếu nhiều ngày, "
	      f"{sum(1 for a in apps if a['half_day'])} nửa ngày)")
	_report_by_type(apps)

	if dry_run:
		print("\n[DRY RUN] không ghi gì. Bỏ `dry_run` để tạo draft.")
		return {"applications": len(apps), "skipped": len(skipped), "warnings": len(warnings)}

	created = existing = 0
	failures = []
	frappe.flags.mute_messages = True
	for i, a in enumerate(apps, 1):
		# Savepoint cho TỪNG đơn: `frappe.db.rollback()` trần sẽ cuốn theo mọi bản ghi tốt
		# chưa commit trong lô — một dòng lỗi ở giữa lô 200 làm mất 199 dòng đã insert.
		frappe.db.savepoint("import_la_row")
		try:
			if _already_there(a):
				existing += 1
				continue
			_insert_draft(a)
			created += 1
		except Exception as e:
			failures.append((a["row"], a["employee"], a["abbr"], str(a["from_date"]),
			                 str(a["to_date"]), str(e).split("\n")[0][:120]))
			frappe.db.rollback(save_point="import_la_row")
		if i % batch_size == 0:
			frappe.db.commit()
			print(f"  ... {i}/{len(apps)}  tạo {created}, bỏ qua {existing}, lỗi {len(failures)}")
	frappe.db.commit()
	frappe.flags.mute_messages = False

	print(f"\nTẠO MỚI (draft): {created} | đã có sẵn: {existing} | LỖI: {len(failures)}")
	_report_failures(failures)
	return {"created": created, "existing": existing, "failed": len(failures), "failures": failures}


def _already_there(a) -> bool:
	return bool(frappe.db.exists("Leave Application", {
		"employee": a["employee"],
		"leave_type": a["leave_type"],
		"from_date": a["from_date"],
		"to_date": a["to_date"],
		"docstatus": ["<", 2],
	}))


def _insert_draft(a):
	doc = frappe.new_doc("Leave Application")
	doc.employee = a["employee"]
	doc.leave_type = a["leave_type"]
	doc.from_date = a["from_date"]
	doc.to_date = a["to_date"]
	if a["half_day"]:
		doc.half_day = 1
		doc.half_day_date = a["from_date"]
	# "Open" = bản nháp chưa duyệt. Cũng tránh `notify_approval_status()`
	# (`hrms/mixins/pwa_notifications.py`) sinh hàng nghìn PWA Notification rác — hàm đó
	# chỉ chạy khi status đổi sang Approved/Rejected và KHÔNG bị chặn bởi
	# `HR Settings.send_leave_notification`.
	doc.status = "Open"
	# ĐÚNG nội dung cột Reason, không thêm gì. Description là thứ HR đọc trên đơn —
	# nhét mã dòng / mã loại nghỉ vào đó chỉ làm bẩn, hai thông tin đó đã có sẵn ở
	# `leave_type` và các cột khác của chính đơn.
	doc.description = a["reason"] or None
	doc.flags.ignore_permissions = True
	doc.insert()


# ---------------------------------------------------------------------------
# B3 — đối chiếu
# ---------------------------------------------------------------------------


def verify(path: str | None = None):
	"""Đối chiếu SỐ ĐƠN theo loại nghỉ giữa file và ERP.

	Đối chiếu theo **số đơn**, không phải số ngày: số ngày do HRMS tự tính (`total_leave_days`)
	có trừ ngày lễ/CN tuỳ `include_holiday` của từng loại, dựng lại công thức đó ở đây chỉ tạo
	thêm một nguồn sự thật thứ hai để lệch nhau. Tổng số ngày vẫn in ra để tham khảo.
	"""
	path = path or DEFAULT_FILE
	rows = _read(path)
	apps, skipped, _w = build_applications(rows, _abbr_map(path))

	file_count = collections.Counter(a["leave_type"] for a in apps)
	erp = frappe.db.sql("""
		SELECT leave_type, COUNT(*) AS n, SUM(total_leave_days) AS days
		FROM `tabLeave Application`
		WHERE docstatus < 2
		GROUP BY leave_type
	""", as_dict=True)
	erp_count = {r.leave_type: r.n for r in erp}
	erp_days = {r.leave_type: float(r.days or 0) for r in erp}

	print(f"{'Loại nghỉ':<56}{'file':>7}{'ERP':>7}{'lệch':>7}{'ngày ERP':>11}")
	total_diff = 0
	for lt in sorted(set(file_count) | set(erp_count)):
		f_n, e_n = file_count.get(lt, 0), erp_count.get(lt, 0)
		diff = e_n - f_n
		total_diff += abs(diff)
		flag = "  ← LỆCH" if diff else ""
		print(f"{lt[:55]:<56}{f_n:>7}{e_n:>7}{diff:>7}{erp_days.get(lt, 0):>11.1f}{flag}")
	print(f"{'TỔNG':<56}{sum(file_count.values()):>7}{sum(erp_count.values()):>7}"
	      f"{sum(erp_count.values()) - sum(file_count.values()):>7}{sum(erp_days.values()):>11.1f}")
	if skipped:
		print(f"\n({len(skipped)} dòng bị loại — xem `run(dry_run=1)` để biết lý do)")
	return {"file": sum(file_count.values()), "erp": sum(erp_count.values()), "diff": total_diff}


# ---------------------------------------------------------------------------
# B4 — submit
# ---------------------------------------------------------------------------


def submit_imported(batch_size: int = 200, limit: int = 0, to_date: str | None = None):
	"""Duyệt + submit các draft đã import.

	🔴 Submit sinh Attendance và ghi Leave Ledger Entry — không quay lại được bằng rollback.
	Sau bước này PHẢI chạy `bulk_update_attendance_optimized` cho toàn khoảng ngày.
	"""
	filters = {"docstatus": 0}
	if to_date:
		# Lọc theo `to_date` chứ không `from_date`: đơn vắt qua mốc sẽ sinh Attendance cho
		# cả những ngày SAU mốc, không nằm trong phạm vi được duyệt.
		filters["to_date"] = ["<=", to_date]
	names = [
		d.name for d in frappe.get_all(
			"Leave Application", filters=filters, fields=["name"],
			order_by="employee, from_date", limit_page_length=int(limit) or 0,
		)
	]
	print(f"Draft cần submit{f' (to_date <= {to_date})' if to_date else ''}: {len(names)}")

	done, failures = 0, []
	frappe.flags.mute_messages = True
	for i, name in enumerate(names, 1):
		frappe.db.savepoint("submit_la_row")
		try:
			doc = frappe.get_doc("Leave Application", name)
			# HRMS chặn submit khi status là Open/Cancelled. Chỉ gán khi cần để
			# `has_value_changed()` không kích hoạt notify_approval_status().
			if doc.status != "Approved":
				doc.status = "Approved"
			doc.flags.ignore_permissions = True
			doc.submit()
			done += 1
		except Exception as e:
			failures.append((name, str(e).split("\n")[0][:120]))
			frappe.db.rollback(save_point="submit_la_row")
		if i % batch_size == 0:
			frappe.db.commit()
			print(f"  ... {i}/{len(names)} submit {done}, lỗi {len(failures)}")
	frappe.db.commit()
	frappe.flags.mute_messages = False

	print(f"\nSUBMIT: {done} | LỖI: {len(failures)}")
	for f in failures[:20]:
		print("   ", f)
	return {"submitted": done, "failed": len(failures), "failures": failures}


# ---------------------------------------------------------------------------
# Báo cáo
# ---------------------------------------------------------------------------


def _report_by_type(apps):
	print("\nSố đơn theo loại nghỉ:")
	for lt, n in collections.Counter(a["leave_type"] for a in apps).most_common():
		print(f"   {n:>6}  {lt}")


def _report_failures(failures):
	if not failures:
		return
	print("\nLỖI (20 dòng đầu):")
	for f in failures[:20]:
		print("   ", f)
	groups = collections.Counter(f[-1].split(":")[0][:70] for f in failures)
	print("\nGom theo thông báo lỗi:")
	for msg, n in groups.most_common():
		print(f"   {n:>5} × {msg}")
