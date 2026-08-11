# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Quy tắc nghỉ phép TIQN — nguồn sự thật DÙNG CHUNG cho hai luồng ghi Attendance.

Hai luồng ghi độc lập vào cùng các field của Attendance:

  A. Leave Application  — `overrides/leave_application/leave_application.py`, chạy khi submit đơn
  B. Engine tính công   — `overrides/shift_type/shift_type_optimized.py`, chạy hourly / bulk

Engine **luôn ghi sau cùng**, nên hai luồng phải ra **cùng một** kết quả, nếu không mỗi FULL run
lại ghi đè kết quả của luồng A. Trước đây mỗi luồng tự quyết định một kiểu — đó là gốc của các
vấn đề 1 · 2 · 3 trong `leave_application/PLAN_LEAVE_OVERRIDE.md`.

Căn cứ nghiệp vụ: `leave_application/QUY_DINH_NGHI_PHEP_2025.md` mục 3.5 và 5.2.
Mọi thay đổi ở file này phải kiểm lại bằng `run_regulation_selftest()`.
"""

import frappe

# Mã tổ hợp nửa ngày theo quy định mục 3.5. Khoá là `frozenset` nên không phụ thuộc thứ tự
# hai đơn nghỉ. KHÔNG suy ra được bằng nối chuỗi: Ốm + KL cho ra "OK/2", không phải "OKL/2".
HALF_DAY_CODE = {
	frozenset({"O", "P"}): "OP/2",
	frozenset({"CO", "P"}): "COP/2",
	frozenset({"O", "CO"}): "OCO/2",
	frozenset({"O", "KL"}): "OK/2",
	frozenset({"CO", "KL"}): "COK/2",
}

_LEAVE_TYPE_CACHE = "tiqn_leave_type_rules"


def _leave_type_map() -> dict:
	"""`{leave_type: {"abbr": str, "is_lwp": int}}`, cache theo site.

	Engine chạy vòng lặp lớn (1.000 NV × 30 ngày) nên tuyệt đối không query mỗi lần.
	"""

	def _build():
		return {
			r.name: {"abbr": r.custom_abbreviation or r.name[:2].upper(), "is_lwp": int(r.is_lwp or 0)}
			for r in frappe.get_all(
				"Leave Type", fields=["name", "custom_abbreviation", "is_lwp"]
			)
		}

	return frappe.cache().get_value(_LEAVE_TYPE_CACHE, _build) or {}


def clear_cache():
	frappe.cache().delete_value(_LEAVE_TYPE_CACHE)


def get_abbreviation(leave_type: str | None) -> str:
	if not leave_type:
		return ""
	row = _leave_type_map().get(leave_type)
	return row["abbr"] if row else leave_type[:2].upper()


def is_unpaid(leave_type: str | None) -> bool:
	"""Loại nghỉ này công ty KHÔNG trả lương? (`is_lwp` — cờ HRMS dùng để trừ lương.)

	`is_lwp = 1` gồm cả nhóm BHXH (`O` `CO` `DS` `TS`) vì tiền do cơ quan BHXH chi trả,
	không phải công ty — xem quy định mục 2.
	"""
	if not leave_type:
		return False
	row = _leave_type_map().get(leave_type)
	return bool(row and row["is_lwp"])


# ---------------------------------------------------------------------------
# Ba quyết định dùng chung
# ---------------------------------------------------------------------------


def resolve_half_day_status(has_checkin: bool, other_leave_type: str | None = None) -> str:
	"""`half_day_status` cho một ngày `Half Day` — quy định mục 5.2.

	    'Present'  nếu nửa còn lại ĐƯỢC CÔNG TY TRẢ LƯƠNG
	    'Absent'   nếu không

	Nửa còn lại được trả lương khi: **đi làm** (có checkin), hoặc là **nghỉ phép có lương**
	(`P` `MC` `HS` `HL`, tức `is_lwp = 0`).

	🔴 `Present` **không** đồng nghĩa "có đi làm". Ca `OP/2` (Ốm ½ + Phép năm ½) cả ngày không
	có checkin nào nhưng vẫn là `Present`, vì nửa còn lại là phép năm — quy định tính công 0,5.
	Quy tắc "không checkin → Absent" sai đúng ở ca này.

	HRMS trừ lương từ hai nguồn độc lập (`salary_slip.py:790` và `:578`), nên gắn sai
	`Absent` sẽ trừ **hai lần** = mất trọn một ngày lương.
	"""
	if has_checkin:
		return "Present"
	if other_leave_type and not is_unpaid(other_leave_type):
		return "Present"
	return "Absent"


def order_leave_types(leave_type_1: str, leave_type_2: str | None = None) -> tuple:
	"""Sắp lại thành `(chính, còn lại)`; **chính** là nửa `is_lwp = 1`.

	`Attendance.leave_type` chỉ giữ được **một** loại, mà HRMS lại chỉ trừ lương theo loại nằm
	ở field đó. Vậy field đó phải là nửa không được trả lương, còn nửa có lương thể hiện qua
	`half_day_status = 'Present'`. Đặt ngược lại thì HRMS bỏ qua cả ngày ⇒ trả đủ lương cho
	ngày chỉ làm nửa buổi.

	Cũng khớp thứ tự chữ của quy định: `OP/2` = Ốm (BHXH) trước, Phép năm sau.
	"""
	if not leave_type_2:
		return leave_type_1, None
	if is_unpaid(leave_type_2) and not is_unpaid(leave_type_1):
		return leave_type_2, leave_type_1
	return leave_type_1, leave_type_2


def combined_abbreviation(leave_type_1: str, leave_type_2: str | None = None) -> str:
	"""Mã in trên bảng công. Một đơn → `"P/2"`; hai đơn → tra `HALF_DAY_CODE`."""
	if not leave_type_1:
		return ""
	a1 = get_abbreviation(leave_type_1)
	if not leave_type_2:
		return f"{a1}/2"
	a2 = get_abbreviation(leave_type_2)
	code = HALF_DAY_CODE.get(frozenset({a1, a2}))
	if code:
		return code
	# Ngoài bảng quy định: nối chuỗi, nửa is_lwp đứng trước (thứ tự đã do order_leave_types lo).
	return f"{a1}{a2}/2" if a1 != a2 else f"{a1}/2"


def full_day_abbreviation(leave_type: str) -> str:
	return get_abbreviation(leave_type)


# ---------------------------------------------------------------------------
# Tự kiểm theo quy định
# ---------------------------------------------------------------------------

# 9 dòng nửa ngày của quy định mục 3.5 + 2 dòng phép năm/hưởng lương mục 3.1-3.2.
# (abbr nửa 1, abbr nửa 2 hoặc None, có checkin) -> (mã, half_day_status, ngày công kỳ vọng)
_REGULATION_HALF_DAY = [
	("P", None, True, "P/2", "Present", 1.0),
	("HL", None, True, "HL/2", "Present", 1.0),
	("O", None, True, "O/2", "Present", 0.5),
	("CO", None, True, "CO/2", "Present", 0.5),
	("O", "P", False, "OP/2", "Present", 0.5),
	("CO", "P", False, "COP/2", "Present", 0.5),
	("O", "CO", False, "OCO/2", "Absent", 0.0),
	("O", "KL", False, "OK/2", "Absent", 0.0),
	("CO", "KL", False, "COK/2", "Absent", 0.0),
]


def _by_abbr() -> dict:
	return {v["abbr"]: k for k, v in _leave_type_map().items()}


def expected_payment_days(leave_type: str, half_day_status: str) -> float:
	"""Ngày công HRMS sẽ tính cho một ngày `Half Day` — tái tạo `salary_slip.py:790` + `:578`."""
	days = 1.0
	if is_unpaid(leave_type):
		days -= 0.5  # calculate_lwp_ppl_and_absent_days_based_on_attendance()
	if half_day_status == "Absent":
		days -= 0.5  # get_half_absent_days()
	return days


def run_regulation_selftest() -> list:
	"""Đối chiếu code với 9 dòng nửa ngày của quy định. Trả về danh sách lỗi (rỗng = đạt)."""
	names = _by_abbr()
	failures = []
	for a1, a2, has_checkin, want_code, want_status, want_days in _REGULATION_HALF_DAY:
		lt1, lt2 = names.get(a1), names.get(a2) if a2 else None
		if not lt1 or (a2 and not lt2):
			failures.append(f"{want_code}: thiếu Leave Type cho mã {a1}/{a2}")
			continue

		primary, other = order_leave_types(lt1, lt2)
		got_code = combined_abbreviation(primary, other)
		got_status = resolve_half_day_status(has_checkin, other)
		got_days = expected_payment_days(primary, got_status)

		if got_code != want_code:
			failures.append(f"{want_code}: mã ra {got_code!r}")
		if got_status != want_status:
			failures.append(f"{want_code}: half_day_status ra {got_status!r}, cần {want_status!r}")
		if abs(got_days - want_days) > 0.01:
			failures.append(f"{want_code}: ngày công ra {got_days}, quy định {want_days}")
	return failures
