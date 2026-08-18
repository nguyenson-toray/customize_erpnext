# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Engine tính số dư phép — nạp ledger của MỘT leave type rồi tính hết trong bộ nhớ.

## Vì sao viết lại

HRMS gọi lại các hàm con cho **từng cặp (nhân viên × leave type)**. Đo trên site TIQN
(1.002 NV Active, 10 Leave Type):

    Employee Leave Balance          180 query/NV  ->  ~107 s  (đã timeout 2 phút/1 department)
    Employee Leave Balance Summary   88 query/NV  ->   ~43 s

Profile 8 NV (1,727 s) cho thấy chỗ tốn **không phải database**:

    get_leave_balance_on (80 lần)   1,035 s   60%
      trong đó validate_leave_access  0,259 s   15%   <- thuần overhead
    get_allocated_and_expired_leaves  0,377 s   22%
    MySQL thực thi                    0,187 s   11%   <- chỉ 11%!
    pypika dựng SQL (prepare_query + _copy)  ~1,0 s

Tức là *dựng* câu SQL tốn ngang *chạy* nó. Nên cách tăng tốc đúng không phải tối ưu SQL mà là
**đừng sinh 977 câu SQL**: toàn bộ ledger của một leave type chỉ ~6.000 dòng — nạp một lần,
group theo nhân viên, rồi tính trong Python.

## Phạm vi: MỘT leave type mỗi lần chạy

Cả hai report có filter `Leave Type`, **mặc định `Phép năm`** — loại duy nhất TIQN cấp
Leave Allocation. Chạy 1 loại thay vì 10 đã giảm 10 lần khối lượng.

Engine dùng được cho **mọi** leave type, kể cả 9 loại nghỉ phát sinh không phân bổ: khi đó
`allocation_record_on()` trả rỗng nên Allocated = 0, Balance = −(đã nghỉ) — đúng y bản HRMS.

⚠ Giá trị mặc định lấy từ cờ `is_earned_leave`, **không hardcode tên** "Phép năm/ Annual leave".

## Bảo toàn con số

`get_leaves_for_period()` của HRMS không cộng `leaves` trong ledger — nó gọi lại
`get_number_of_leave_days()` (xử lý nửa ngày + ngày lễ) sau khi **cắt** entry theo biên kỳ.
Với entry nằm **trọn** trong kỳ thì `leaves` trong ledger đã chính là con số đó — đã kiểm 60/60
nhân viên khớp tuyệt đối, và kỳ 2025-12-26→2026-12-25 có **0** entry vắt qua biên.

Nhưng vắt biên **vẫn có thể xảy ra** ở kỳ khác. Nên: hễ một nhân viên có entry vắt biên thì
**giao cả nhân viên đó cho hàm gốc của HRMS** (`leaves_taken()` gọi lại `get_leaves_for_period`)
— chậm nhưng đúng, và chỉ áp cho đúng những người đó.
"""

from collections import defaultdict

import frappe
from frappe.utils import flt, getdate


def get_annual_leave_types() -> list[str]:
	"""Các Leave Type được phân bổ theo năm — hiện tại đúng 1 loại (`Phép năm`)."""
	return frappe.get_all(
		"Leave Type", filters={"is_earned_leave": 1}, pluck="name", order_by="name"
	)


def resolve_leave_types(filters) -> list[str]:
	"""Leave type mà lần chạy này xử lý.

	Ưu tiên filter người dùng chọn; bỏ trống thì rơi về phép năm (mặc định của filter, nên
	trường hợp rỗng chỉ xảy ra khi gọi từ script hoặc user tự xoá ô chọn).
	"""
	chosen = filters.get("leave_type")
	if chosen:
		return [chosen] if isinstance(chosen, str) else list(chosen)
	return get_annual_leave_types()


class LeaveBalanceEngine:
	"""Toàn bộ ledger + allocation của MỘT leave type, tính trong bộ nhớ.

	Số query là **hằng số** (3), không phụ thuộc số nhân viên.
	"""

	def __init__(self, leave_type: str, employees: list[str] | None = None):
		self.leave_type = leave_type
		self.employees = set(employees) if employees else None

		self.ledger = defaultdict(list)      # employee -> [dòng ledger]
		self.allocations = defaultdict(list)  # employee -> [Leave Allocation đã submit]

		self._load_ledger()
		self._load_allocations()

	# ------------------------------------------------------------------ nạp
	def _load_ledger(self):
		cond, params = "", {"lt": self.leave_type}
		if self.employees is not None:
			cond = " AND employee IN %(emps)s"
			params["emps"] = tuple(self.employees) or ("",)

		rows = frappe.db.sql(
			f"""
			SELECT employee, transaction_type, transaction_name, from_date, to_date,
			       leaves, is_carry_forward, is_expired, holiday_list
			FROM `tabLeave Ledger Entry`
			WHERE docstatus = 1 AND leave_type = %(lt)s {cond}
			ORDER BY employee, from_date, name
			""",
			params,
			as_dict=True,
		)
		for r in rows:
			r.from_date = getdate(r.from_date)
			r.to_date = getdate(r.to_date) if r.to_date else None
			self.ledger[r.employee].append(r)

	def _load_allocations(self):
		cond, params = "", {"lt": self.leave_type}
		if self.employees is not None:
			cond = " AND employee IN %(emps)s"
			params["emps"] = tuple(self.employees) or ("",)

		rows = frappe.db.sql(
			f"""
			SELECT name, employee, from_date, to_date, total_leaves_allocated, unused_leaves
			FROM `tabLeave Allocation`
			WHERE docstatus = 1 AND leave_type = %(lt)s {cond}
			ORDER BY employee, to_date
			""",
			params,
			as_dict=True,
		)
		for r in rows:
			r.from_date = getdate(r.from_date)
			r.to_date = getdate(r.to_date)
			self.allocations[r.employee].append(r)

	# --------------------------------------------------- vắt biên -> fallback
	def has_straddling_entry(self, employee: str, from_date, to_date) -> bool:
		"""Có entry nghỉ nào bị biên kỳ cắt ngang không (xem docstring module)."""
		f, t = getdate(from_date), getdate(to_date)
		for e in self.ledger.get(employee, ()):
			if e.transaction_type != "Leave Application":
				continue
			if e.to_date is None:
				continue
			overlaps = e.from_date <= t and e.to_date >= f
			if overlaps and (e.from_date < f or e.to_date > t):
				return True
		return False

	def leaves_taken(self, employee: str, from_date, to_date) -> float:
		"""Số ngày đã nghỉ trong kỳ, **số dương** (ledger lưu số âm).

		Trả về giá trị tương đương `-get_leaves_for_period(...)` của HRMS.
		"""
		if self.has_straddling_entry(employee, from_date, to_date):
			from hrms.hr.doctype.leave_application.leave_application import get_leaves_for_period

			return flt(get_leaves_for_period(employee, self.leave_type, from_date, to_date)) * -1

		f, t = getdate(from_date), getdate(to_date)
		total = 0.0
		for e in self.ledger.get(employee, ()):
			if e.transaction_type != "Leave Application" or e.leaves >= 0:
				continue
			if e.from_date >= f and e.to_date is not None and e.to_date <= t:
				total += flt(e.leaves)
		return total * -1

	# ------------------------------------------------ 3 cột phân bổ / hết hạn
	def allocated(self, employee: str, from_date, to_date) -> float:
		"""Khớp `get_allocated_leaves`: Allocation + Adjustment, chưa hết hạn, không CF."""
		f, t = getdate(from_date), getdate(to_date)
		return sum(
			flt(e.leaves)
			for e in self.ledger.get(employee, ())
			if e.transaction_type in ("Leave Allocation", "Leave Adjustment")
			and not e.is_expired
			and not e.is_carry_forward
			and f <= e.from_date <= t
		)

	def expired(self, employee: str, from_date, to_date) -> float:
		"""Khớp `get_expired_leaves`: ABS(SUM) — from_date HOẶC to_date nằm trong kỳ."""
		f, t = getdate(from_date), getdate(to_date)
		total = sum(
			flt(e.leaves)
			for e in self.ledger.get(employee, ())
			if e.transaction_type == "Leave Allocation"
			and e.is_expired
			and ((f <= e.from_date <= t) or (e.to_date is not None and f <= e.to_date <= t))
		)
		return abs(total)

	def carry_forwarded(self, employee: str, from_date, to_date) -> float:
		"""Khớp `get_cf_leaves`: Allocation, chưa hết hạn, is_carry_forward = 1."""
		f, t = getdate(from_date), getdate(to_date)
		return sum(
			flt(e.leaves)
			for e in self.ledger.get(employee, ())
			if e.transaction_type == "Leave Allocation"
			and not e.is_expired
			and e.is_carry_forward
			and f <= e.from_date <= t
		)

	# ------------------------------------------------------- số dư đầu kỳ
	def previous_allocation(self, employee: str, before_date):
		"""Khớp `get_previous_allocation`: allocation gần nhất có to_date < before_date."""
		d = getdate(before_date)
		prev = [a for a in self.allocations.get(employee, ()) if a.to_date < d]
		return max(prev, key=lambda a: a.to_date) if prev else None

	def allocation_record_on(self, employee: str, date):
		"""Khớp `get_leave_allocation_records(employee, date, leave_type)`.

		Gộp các dòng ledger loại Allocation/Adjustment còn hiệu lực tại `date`:
		 · dòng mới (is_carry_forward=0) thì to_date >= date
		 · dòng CF thì to_date phải nằm trong khoảng của Leave Allocation chứa nó
		"""
		d = getdate(date)
		cf = new = 0.0
		froms, tos = [], []

		alloc_range = {a.name: (a.from_date, a.to_date) for a in self.allocations.get(employee, ())}

		for e in self.ledger.get(employee, ()):
			if e.transaction_type not in ("Leave Allocation", "Leave Adjustment"):
				continue
			if e.is_expired or e.from_date > d:
				continue

			if not e.is_carry_forward:
				if e.to_date is None or e.to_date < d:
					continue
			else:
				rng = alloc_range.get(e.transaction_name)
				if not rng:
					continue
				a_from, a_to = rng
				if not (e.to_date and a_from <= e.to_date <= a_to):
					continue
				if not (a_from <= d <= a_to):
					continue

			if e.is_carry_forward:
				cf += flt(e.leaves)
			else:
				new += flt(e.leaves)

			froms.append(e.from_date)
			if e.to_date:
				tos.append(e.to_date)

		if not froms:
			return frappe._dict()

		return frappe._dict(
			employee=employee,
			leave_type=self.leave_type,
			from_date=min(froms),
			to_date=max(tos) if tos else None,
			total_leaves_allocated=cf + new,
			unused_leaves=cf,
			new_leaves_allocated=new,
		)

	def cf_expiry(self, employee: str, to_date, alloc_from_date):
		"""Khớp `get_allocation_expiry_for_cf_leaves`."""
		if not alloc_from_date:
			return ""
		f, t = getdate(alloc_from_date), getdate(to_date)
		for e in self.ledger.get(employee, ()):
			if (
				e.is_carry_forward
				and e.transaction_type == "Leave Allocation"
				and e.to_date is not None
				and f <= e.to_date <= t
			):
				return e.to_date
		return ""

	def manually_expired(self, employee: str, from_date, end_date) -> float:
		"""Khớp `get_manually_expired_leaves` — lưu ý HRMS lấy DÒNG ĐẦU, không SUM."""
		if not from_date:
			return 0.0
		f, t = getdate(from_date), getdate(end_date)
		for e in self.ledger.get(employee, ()):
			if (
				e.transaction_type == "Leave Allocation"
				and e.is_expired
				and not e.is_carry_forward
				and e.from_date >= f
				and e.to_date is not None
				and e.to_date < t
			):
				return flt(e.leaves)
		return 0.0

	def balance_on(self, employee: str, date) -> float:
		"""Khớp `get_leave_balance_on(employee, leave_type, date)` (không consumption).

		Bỏ `validate_leave_access()` — report chỉ chạy cho người có quyền xem report, và
		HRMS cũng đã lọc nhân viên bằng `frappe.get_list` ở bước trước.
		"""
		d = getdate(date)
		alloc = self.allocation_record_on(employee, d)
		if not alloc:
			return 0.0

		expiry = self.cf_expiry(employee, frappe.utils.nowdate(), alloc.from_date)
		taken = self.leaves_taken(employee, alloc.from_date, d) * -1  # về lại số âm như HRMS
		manual = self.manually_expired(employee, alloc.from_date, d)

		if expiry and alloc.unused_leaves:
			# Kỳ có cả phép chuyển sang và phép mới -> giao cho HRMS, nhánh này nhiều ngoại lệ
			# và TIQN hiện có 0 dòng is_carry_forward nên không đáng tự viết lại.
			from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on

			return flt(get_leave_balance_on(employee, self.leave_type, d))

		return flt(alloc.total_leaves_allocated) + flt(taken) + flt(manual)
