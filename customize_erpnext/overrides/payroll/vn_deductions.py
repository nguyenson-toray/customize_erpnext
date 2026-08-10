# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Khấu trừ theo pháp luật Việt Nam — BHXH/BHYT/BHTN, đoàn phí, thuế TNCN.

Móc vào `apply_regional_deductions` của HRMS (`salary_slip.py:877`, decorator
`@hrms.allow_regional`), đăng ký qua `regional_overrides` cho region `"Vietnam"`.
Cách làm học từ `frappe/india-payroll`. Xem `overrides/payroll_docs/PLAN_PAYROLL_SETTINGS.md`.

Vì sao tính ở đây thay vì bằng formula trong Salary Structure:
`COMPONENT_EVAL_GLOBALS` (`hrms/payroll/utils.py:34`) chỉ cho phép int/float/round/date/
min/max — formula **không đọc được** Settings, không truy cập DB, không đếm được người
phụ thuộc. Ở đây là Python thuần nên đọc được tất cả.

⚠ Hook chạy **sau** khi `gross_pay` đã chốt (`salary_slip.py:859`) nên chỉ thêm được
**deduction**. Dòng `7.6` hoàn 21,5% là *earning* nên vẫn phải nằm trong Salary Structure.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_first_day, get_last_day, getdate

from customize_erpnext.customize_erpnext.doctype.employee_dependent.employee_dependent import (
	get_dependent_count,
)
from customize_erpnext.customize_erpnext.doctype.tiqn_payroll_settings.tiqn_payroll_settings import (
	calculate_pit,
	get_effective_row,
	get_settings,
	is_on_probation,
)

SI_COMPONENT = "6.1 SI/BHXH (8%)"
HI_COMPONENT = "6.2 HI/BHYT (1,5%)"
UI_COMPONENT = "6.3 UI/BHTN (1%)"
UNION_FEE_COMPONENT = "6.4 Union Fee/ Phí Công Đoàn"
PIT_COMPONENT = "6.5 PIT/Thuế TNCN"

INSURANCE_COMPONENTS = (SI_COMPONENT, HI_COMPONENT, UI_COMPONENT)
ALL_COMPONENTS = INSURANCE_COMPONENTS + (UNION_FEE_COMPONENT, PIT_COMPONENT)

# Trần đóng bảo hiểm = bội số này × mức lương cơ sở (khi bật `apply_si_ceiling`)
SI_CEILING_MULTIPLIER = 20


def apply_regional_deductions(doc) -> None:
	"""Điểm vào duy nhất của hook. Thứ tự có ý nghĩa: PIT cần số bảo hiểm đã tính."""
	if not doc.salary_structure:
		return

	insurance = apply_insurance_and_union_fee(doc)
	apply_personal_income_tax(doc, insurance_deducted=insurance)


# ---------------------------------------------------------------------------
# Bảo hiểm bắt buộc + đoàn phí
# ---------------------------------------------------------------------------


def apply_insurance_and_union_fee(doc) -> float:
	"""Trả về tổng BHXH+BHYT+BHTN đã trừ (PIT cần con số này để tính thu nhập tính thuế).

	Khi tính năng còn tắt, vẫn phải **đọc** số bảo hiểm đang có trên phiếu (do formula
	trong Salary Structure sinh ra) để PIT tính đúng — nếu không, bật PIT mà chưa bật
	bảo hiểm sẽ ra thuế cao vọt.
	"""
	settings = get_settings()
	if not settings.enable_insurance_auto:
		existing = _sum_existing(doc, INSURANCE_COMPONENTS)
		if not existing and not is_on_probation(_employment_type(doc)):
			# Lưới an toàn: dòng 6.1–6.3 đã được gỡ khỏi Salary Structure, nên tắt cờ này
			# nghĩa là KHÔNG trừ bảo hiểm cho ai cả — hỏng âm thầm, không báo lỗi gì.
			frappe.msgprint(
				_("Phiếu lương không có dòng bảo hiểm nào, mà <b>Auto-calculate Insurance</b> "
				  "trong TIQN Payroll Settings đang TẮT. Nhân viên chính thức sẽ không bị trừ "
				  "BHXH/BHYT/BHTN."),
				title=_("Thiếu khấu trừ bảo hiểm"),
				indicator="red",
			)
		return existing

	if not _components_exist(doc, INSURANCE_COMPONENTS + (UNION_FEE_COMPONENT,)):
		return _sum_existing(doc, INSURANCE_COMPONENTS)

	probation = is_on_probation(_employment_type(doc))
	if probation:
		# Thử việc: chưa đóng BH lẫn đoàn phí. Phần công ty đóng được hoàn lại bằng tiền
		# qua dòng 7.6 trong Salary Structure (earning — hook không thêm được).
		_remove(doc, INSURANCE_COMPONENTS + (UNION_FEE_COMPONENT,))
		return 0.0

	if not is_insurance_due(doc, settings):
		# Không đóng BH tháng này -> cũng không thu đoàn phí, vì không có lương để trừ.
		_remove(doc, INSURANCE_COMPONENTS + (UNION_FEE_COMPONENT,))
		return 0.0

	rate = get_effective_row("insurance", doc.end_date)
	if not rate:
		frappe.msgprint(
			_("Chưa khai tỷ lệ bảo hiểm có hiệu lực đến {0} trong TIQN Payroll Settings.").format(
				frappe.format(doc.end_date, {"fieldtype": "Date"})
			),
			indicator="orange",
			alert=True,
		)
		return _sum_existing(doc, INSURANCE_COMPONENTS)

	si_base = _si_base(doc, settings)
	amounts = {
		SI_COMPONENT: flt(si_base * flt(rate.si_percent) / 100.0, 0),
		HI_COMPONENT: flt(si_base * flt(rate.hi_percent) / 100.0, 0),
		UI_COMPONENT: flt(si_base * flt(rate.ui_percent) / 100.0, 0),
	}
	for component, amount in amounts.items():
		_upsert(doc, component, amount)

	_upsert(doc, UNION_FEE_COMPONENT, flt(settings.union_fee_amount, 0))
	return sum(amounts.values())


def is_insurance_due(doc, settings) -> bool:
	"""Tháng này có phải đóng BHXH/BHYT/BHTN không — theo **mốc 14 ngày** của Luật BHXH 2024.

	Quy tắc (`PAYROLL_SETUP.md` mục 2.6):
	    nghỉ **không hưởng lương** >= 14 ngày làm việc trong tháng  ->  KHÔNG đóng
	    dưới 14 ngày                                               ->  đóng ĐỦ cả tháng

	🔴 Đếm theo **THÁNG DƯƠNG LỊCH**, không theo kỳ lương. Cơ quan BHXH tính từ ngày 01
	đến cuối tháng, còn kỳ lương TIQN là 26 → 25. Lấy tháng của `end_date` vì đó là tháng
	mà kỳ lương đại diện (kỳ 26/06→25/07 là *tháng 7*).

	Ngày **hưởng nguyên lương** (phép năm, lễ Tết) vẫn tính là có làm việc — chỉ ngày
	**không hưởng lương** mới đếm vào mốc.
	"""
	threshold = flt(settings.unpaid_days_to_skip_insurance)
	if not threshold:
		return True
	return count_unpaid_working_days(doc, getdate(doc.end_date)) < threshold


def count_unpaid_working_days(doc, as_on) -> float:
	"""Số ngày làm việc **không hưởng lương** trong tháng dương lịch chứa `as_on`.

	Ngày làm việc = ngày trong tháng **trừ Chủ Nhật** (quy tắc TIQN, mục 2.2).
	Ngày lễ vẫn là ngày làm việc **có hưởng lương** nên không tính vào đây.

	Tính là không hưởng lương:
	    - ngoài thời gian làm việc (trước ngày vào làm / sau ngày nghỉ việc)
	    - `Absent`
	    - `On Leave` với loại nghỉ **không lương** (`Leave Type.is_lwp = 1`)
	    - `Half Day` có `half_day_status = "Absent"`  -> tính **0,5**
	    - không có bản ghi chấm công (theo `Payroll Settings.consider_unmarked_attendance_as`)
	"""
	month_start, month_end = get_first_day(as_on), get_last_day(as_on)
	weekly_offs = _weekly_off_dates(doc, month_start, month_end)

	attendance = {
		row.attendance_date: row
		for row in frappe.get_all(
			"Attendance",
			filters={"employee": doc.employee, "docstatus": 1,
			         "attendance_date": ("between", [month_start, month_end])},
			fields=["attendance_date", "status", "half_day_status", "leave_type"],
			order_by="attendance_date asc",
		)
	}
	lwp_types = _unpaid_leave_types()
	unmarked_is_absent = (
		frappe.db.get_single_value("Payroll Settings", "consider_unmarked_attendance_as") == "Absent"
	)
	joining, relieving = _employment_window(doc.employee)

	unpaid = 0.0
	day = month_start
	while day <= month_end:
		if day in weekly_offs:
			day = frappe.utils.add_days(day, 1)
			continue

		if (joining and day < joining) or (relieving and day > relieving):
			unpaid += 1                       # chưa vào làm / đã nghỉ việc
		else:
			row = attendance.get(day)
			if row is None:
				unpaid += 1 if unmarked_is_absent else 0
			elif row.status == "Absent":
				unpaid += 1
			elif row.status == "On Leave" and row.leave_type in lwp_types:
				unpaid += 1
			elif row.status == "Half Day" and row.half_day_status == "Absent":
				unpaid += 0.5
		day = frappe.utils.add_days(day, 1)
	return unpaid


def _weekly_off_dates(doc, from_date, to_date) -> set:
	"""Chủ Nhật trong khoảng — dùng lại `CustomSalarySlip._holiday_map()` để một nơi
	duy nhất quyết định ngày nào là ngày nghỉ hằng tuần."""
	if hasattr(doc, "_holiday_map"):
		return {d for d, weekly_off in doc._holiday_map(from_date, to_date).items() if weekly_off}
	return set()


def _unpaid_leave_types() -> set:
	return set(frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name"))


def _employment_window(employee: str) -> tuple:
	row = frappe.db.get_value("Employee", employee,
	                          ["date_of_joining", "relieving_date"], as_dict=True) or {}
	return (getdate(row.date_of_joining) if row.get("date_of_joining") else None,
	        getdate(row.relieving_date) if row.get("relieving_date") else None)


def _si_base(doc, settings) -> float:
	"""Mức lương đóng bảo hiểm, đã áp trần nếu công ty có áp.

	TIQN hiện **không** áp trần — đã đối chiếu: phiếu TIQN-0002 có căn cứ 47.652.438,
	cao hơn trần 20 × lương cơ sở, nhưng vẫn đóng trên toàn bộ (BHXH 3.812.195, không
	phải 3.744.000). Giữ nhánh áp trần vì luật có quy định và công ty có thể đổi.
	"""
	si_base = flt(_ssa_value(doc, "custom_si_base"))
	if settings.apply_si_ceiling:
		ceiling = flt(settings.base_salary) * SI_CEILING_MULTIPLIER
		if ceiling and si_base > ceiling:
			return ceiling
	return si_base


# ---------------------------------------------------------------------------
# Thuế thu nhập cá nhân
# ---------------------------------------------------------------------------


def apply_personal_income_tax(doc, insurance_deducted: float = 0.0) -> None:
	"""Khấu trừ thuế TNCN theo biểu luỹ tiến **tháng**.

	KHÔNG dùng `Income Tax Slab` của HRMS: HRMS tính trên thu nhập cả năm rồi chia cho
	số kỳ còn lại (mô hình Ấn Độ), còn Việt Nam khấu trừ theo biểu tháng và quyết toán
	lại cuối năm. Hai cách chỉ trùng nhau khi thu nhập đều tất cả các tháng.
	"""
	settings = get_settings()
	if not settings.enable_pit_auto:
		return

	if not _components_exist(doc, (PIT_COMPONENT,)):
		return

	if is_on_probation(_employment_type(doc)):
		_upsert(doc, PIT_COMPONENT, _probation_withholding(doc, settings))
		return

	rate = get_effective_row("deduction", doc.end_date)
	if not rate:
		frappe.msgprint(
			_("Chưa khai mức giảm trừ gia cảnh có hiệu lực đến {0} trong TIQN Payroll Settings.").format(
				frappe.format(doc.end_date, {"fieldtype": "Date"})
			),
			indicator="orange",
			alert=True,
		)
		return

	dependents = get_dependent_count(doc.employee, doc.end_date)
	taxable = (
		get_taxable_earnings(doc)
		- flt(insurance_deducted)
		- flt(rate.personal_deduction)
		- dependents * flt(rate.dependent_deduction)
	)
	_upsert(doc, PIT_COMPONENT, calculate_pit(taxable, doc.end_date))


def _probation_withholding(doc, settings) -> float:
	"""Khấu trừ thuế cố định cho người lao động đang thử việc.

	Hợp đồng thử việc 30/60 ngày là hợp đồng **dưới 3 tháng**, thuộc diện khấu trừ theo
	thuế suất cố định trên thu nhập chi trả (TT 111/2013/TT-BTC Điều 25):

	    - **KHÔNG** áp biểu luỹ tiến
	    - **KHÔNG** có giảm trừ bản thân / người phụ thuộc
	    - **KHÔNG** trừ bảo hiểm (thử việc chưa đóng)
	    - Chi trả dưới ngưỡng tối thiểu thì không khấu trừ

	Người lao động **tự quyết toán** với cơ quan thuế vào tháng 4 năm sau — đây chỉ là
	tạm khấu trừ, không phải số thuế cuối cùng.
	"""
	taxable = get_taxable_earnings(doc)
	if taxable < flt(settings.probation_tax_min_income):
		return 0.0
	return flt(taxable * flt(settings.probation_tax_rate) / 100.0, 0)


def get_taxable_earnings(doc) -> float:
	"""Tổng các dòng earning có `is_tax_applicable = 1`.

	Đọc **cờ**, không liệt kê tên khoản — cờ đã khai đúng ở cấp Salary Component
	(`PAYROLL_SETUP.md` mục 4.1). Nhờ vậy thêm/bớt phụ cấp không phải sửa code này.

	Theo Điều 4 Luật Thuế TNCN 2025 + Điều 26 NĐ 253/2026, tiền làm thêm giờ được
	**miễn toàn bộ** — nên 3 dòng OT để `is_tax_applicable = 0` và tự động rơi ra ngoài.
	"""
	total = 0.0
	for row in doc.earnings:
		if row.do_not_include_in_total:
			continue
		if _is_tax_applicable(row):
			total += flt(row.amount)
	return total


def _is_tax_applicable(row) -> bool:
	"""Cờ trên dòng phiếu; dòng từ Additional Salary có thể chưa được set nên đọc lại
	từ Salary Component."""
	if row.get("is_tax_applicable") is not None:
		return bool(row.is_tax_applicable)
	return bool(
		frappe.get_cached_value("Salary Component", row.salary_component, "is_tax_applicable")
	)


# ---------------------------------------------------------------------------
# Tiện ích
# ---------------------------------------------------------------------------


def _employment_type(doc) -> str | None:
	return frappe.get_cached_value("Employee", doc.employee, "employment_type")


def _ssa_value(doc, fieldname):
	"""Đọc field trên Salary Structure Assignment có hiệu lực tại `end_date`.

	Dùng `end_date` chứ không phải `start_date`: kỳ lương 26/06 -> 25/07 là tháng 7.
	"""
	row = frappe.db.get_value(
		"Salary Structure Assignment",
		{
			"employee": doc.employee,
			"salary_structure": doc.salary_structure,
			"from_date": ("<=", doc.end_date),
			"docstatus": 1,
		},
		fieldname,
		order_by="from_date desc",
	)
	return row


def _components_exist(doc, components) -> bool:
	"""Thiếu component thì cảnh báo và bỏ qua — KHÔNG throw.

	Throw ở đây sẽ làm gãy cả kỳ lương 1000 người chỉ vì một component bị xoá nhầm.
	"""
	missing = [c for c in components if not frappe.db.exists("Salary Component", c)]
	if missing:
		frappe.msgprint(
			_("Thiếu Salary Component: {0}. Bỏ qua phần tính tự động.").format(
				", ".join(frappe.bold(m) for m in missing)
			),
			indicator="orange",
			alert=True,
		)
		return False
	return True


def _sum_existing(doc, components) -> float:
	return sum(flt(d.amount) for d in doc.deductions if d.salary_component in components)


def _remove(doc, components) -> None:
	doc.deductions = [d for d in doc.deductions if d.salary_component not in components]


def _upsert(doc, component: str, amount: float) -> None:
	"""Xoá dòng cũ RỒI mới thêm — bắt buộc phải idempotent.

	Salary Slip được tính lại nhiều lần (save, đổi ngày công, Payroll Entry chạy lại).
	Append mà không xoá là **nhân đôi khấu trừ**, và sẽ không ai phát hiện cho tới khi
	người lao động thắc mắc. Xoá cả khi amount = 0 để dòng cũ không nằm lại khi nhân
	viên chuyển sang diện không phải đóng.
	"""
	_remove(doc, (component,))
	if flt(amount) > 0:
		doc.append("deductions", {"salary_component": component, "amount": flt(amount)})
