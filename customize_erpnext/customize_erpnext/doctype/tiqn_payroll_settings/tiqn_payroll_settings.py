# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Hằng số lương của TIQN — do HR quản lý.

Tách khỏi `Payroll Settings` của HRMS (IT Admin set một lần, hành vi Payroll Entry).
Xem `overrides/payroll_docs/PLAN_PAYROLL_SETTINGS.md`.

Ba bảng con có **ngày hiệu lực** vì mức tiền do pháp luật quy định thay đổi theo thời
gian, và tính lại kỳ lương cũ phải ra đúng số cũ:
    - Mức giảm trừ gia cảnh   (11tr/4,4tr -> 15,5tr/6,2tr từ kỳ tính thuế 2026)
    - Biểu thuế luỹ tiến
    - Tỷ lệ BHXH/BHYT/BHTN

Quy ước `as_on`: dùng **`end_date` của Salary Slip**, không phải `start_date`.
Kỳ lương 26/06 -> 25/07 là **tháng 7**; lấy start_date sẽ lệch một tháng.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

SETTINGS = "TIQN Payroll Settings"

# Bảng con có ngày hiệu lực -> field chứa nó
EFFECTIVE_TABLES = {
	"deduction": "deduction_rates",
	"insurance": "insurance_rates",
}


class TIQNPayrollSettings(Document):
	def validate(self):
		self.validate_effective_dates()
		self.validate_tax_brackets()

	def validate_effective_dates(self):
		"""Mỗi bảng phải có ít nhất 1 dòng, và không trùng ngày hiệu lực."""
		for label, fieldname in EFFECTIVE_TABLES.items():
			rows = self.get(fieldname) or []
			if not rows:
				frappe.throw(
					_("{0}: cần ít nhất một dòng có ngày hiệu lực.").format(
						_(self.meta.get_label(fieldname))
					)
				)
			seen = {}
			for row in rows:
				key = getdate(row.from_date)
				if key in seen:
					frappe.throw(
						_("{0}: ngày hiệu lực {1} bị khai hai lần (dòng {2} và {3}).").format(
							_(self.meta.get_label(fieldname)),
							frappe.format(key, {"fieldtype": "Date"}),
							seen[key],
							row.idx,
						)
					)
				seen[key] = row.idx

	def validate_tax_brackets(self):
		"""Biểu thuế: mỗi mốc hiệu lực phải liền mạch và bậc cuối phải hở trên."""
		by_date = {}
		for row in self.tax_brackets or []:
			by_date.setdefault(getdate(row.from_date), []).append(row)

		for from_date, rows in by_date.items():
			rows.sort(key=lambda r: flt(r.income_from))
			label = frappe.format(from_date, {"fieldtype": "Date"})

			if not any(flt(r.income_to) == 0 for r in rows):
				frappe.throw(
					_("Biểu thuế hiệu lực {0}: bậc cuối phải để <b>Monthly Income To = 0</b> "
					  "(không giới hạn trên), nếu không thu nhập cao sẽ không rơi vào bậc nào.").format(label)
				)

			for prev, cur in zip(rows, rows[1:]):
				if flt(prev.income_to) == 0:
					frappe.throw(
						_("Biểu thuế hiệu lực {0}: bậc {1} để hở trên nhưng vẫn còn bậc phía sau.").format(
							label, prev.bracket
						)
					)
				if flt(cur.income_from) != flt(prev.income_to):
					frappe.throw(
						_("Biểu thuế hiệu lực {0}: bậc {1} kết thúc ở {2} nhưng bậc {3} bắt đầu ở {4} "
						  "— khoảng thu nhập bị hở hoặc chồng nhau.").format(
							label, prev.bracket,
							frappe.format(prev.income_to, {"fieldtype": "Currency"}),
							cur.bracket,
							frappe.format(cur.income_from, {"fieldtype": "Currency"}),
						)
					)

	def on_update(self):
		frappe.cache().delete_value(_CACHE_KEY)


# ---------------------------------------------------------------------------
# Tra cứu
# ---------------------------------------------------------------------------

_CACHE_KEY = "tiqn_payroll_settings"


def get_settings() -> "Document":
	"""Bản Settings đã cache trong request. Dùng `frappe.get_cached_doc` nên tự
	invalidate khi HR save (Frappe clear document cache trong `on_update`)."""
	return frappe.get_cached_doc(SETTINGS)


def get_effective_row(table: str, as_on) -> "frappe._dict":
	"""Dòng có `from_date` lớn nhất mà vẫn <= `as_on`.

	`table` là khoá trong EFFECTIVE_TABLES ("deduction" | "insurance").
	Trả về `frappe._dict` rỗng nếu chưa khai mốc nào áp dụng được — hàm gọi phải
	tự xử lý, KHÔNG throw ở đây để một Settings thiếu dòng không làm gãy cả kỳ lương.
	"""
	fieldname = EFFECTIVE_TABLES.get(table)
	if not fieldname:
		frappe.throw(_("Unknown effective table: {0}").format(table))

	as_on = getdate(as_on)
	best = None
	for row in get_settings().get(fieldname) or []:
		if getdate(row.from_date) <= as_on and (
			best is None or getdate(row.from_date) > getdate(best.from_date)
		):
			best = row
	return frappe._dict(best.as_dict()) if best else frappe._dict()


def get_tax_brackets(as_on) -> list:
	"""Biểu thuế của mốc hiệu lực áp dụng cho `as_on`, đã sắp theo `income_from`."""
	as_on = getdate(as_on)
	dates = {getdate(r.from_date) for r in get_settings().tax_brackets or []}
	applicable = [d for d in dates if d <= as_on]
	if not applicable:
		return []
	chosen = max(applicable)
	rows = [r for r in get_settings().tax_brackets if getdate(r.from_date) == chosen]
	return sorted(rows, key=lambda r: flt(r.income_from))


def calculate_pit(taxable_income: float, as_on) -> float:
	"""Thuế TNCN của MỘT kỳ lương theo biểu luỹ tiến tháng.

	Dùng cách rút gọn của Bộ Tài chính: `thu nhập × thuế suất - số trừ nhanh`.
	Trả 0 khi thu nhập tính thuế <= 0 hoặc chưa khai biểu thuế.
	"""
	taxable_income = flt(taxable_income)
	if taxable_income <= 0:
		return 0.0

	for row in get_tax_brackets(as_on):
		upper = flt(row.income_to)
		if upper == 0 or taxable_income <= upper:
			return max(
				0.0,
				flt(taxable_income * flt(row.rate_percent) / 100.0 - flt(row.quick_deduction), 0),
			)
	return 0.0


def get_probation_employment_types() -> list:
	"""Danh sách Employment Type coi là thử việc.

	Trước đây chuỗi này lặp ở 6 chỗ trong formula Salary Structure — thêm một loại HĐ
	thử việc mới mà sót một chỗ là âm thầm trừ sai bảo hiểm. Nay khai một nơi duy nhất.
	"""
	return [
		row.employment_type
		for row in get_settings().probation_employment_types or []
		if row.employment_type
	]


def is_on_probation(employment_type: str | None) -> bool:
	return bool(employment_type) and employment_type in get_probation_employment_types()
