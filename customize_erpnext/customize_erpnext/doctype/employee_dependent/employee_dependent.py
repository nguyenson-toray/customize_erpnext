# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Hồ sơ người phụ thuộc (NPT) của một nhân viên — giảm trừ gia cảnh thuế TNCN.

Xem `overrides/payroll_docs/PLAN_EMPLOYEE_DEPENDENT.md`.

**Mỗi nhân viên có đúng MỘT bản ghi**; danh sách NPT nằm ở child table `dependents`
(`Employee Dependent Item`). Uniqueness do `autoname = field:employee` bảo đảm —
docname chính là mã nhân viên, nên không cần validate riêng.

**Phạm vi dữ liệu:** ERP chỉ lưu **vừa đủ để tính lương**. HR vẫn kê khai với cơ quan
thuế bằng phần mềm riêng, chi tiết hơn (MST NPT, loại giấy tờ, hồ sơ chứng minh...) —
những thứ đó **không** nhân bản vào đây.

Ba nguyên tắc pháp lý chi phối thiết kế:
  1. Mỗi NPT chỉ được tính cho **01** người nộp thuế trong **cùng năm tính thuế**
  2. Không giới hạn số lượng NPT
  3. Áp dụng **từ THÁNG** phát sinh nghĩa vụ nuôi dưỡng

Nguyên tắc 3 là lý do mỗi dòng có `from_date`/`to_date` thay vì một field Int đếm số
NPT: số NPT thay đổi giữa năm, tính lại kỳ lương cũ phải ra đúng số NPT của kỳ đó.

Nguyên tắc 1 là lý do khoá chống trùng là `id_number` (số định danh / số giấy khai
sinh) chứ KHÔNG phải MST — MST NPT chỉ có nếu đã từng được cấp.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Coalesce
from frappe.utils import get_first_day, get_link_to_form, getdate


class EmployeeDependent(Document):
	def validate(self):
		self.normalize_from_dates()
		self.validate_periods()
		self.validate_no_overlap_within_record()
		self.validate_not_claimed_by_other_employee()
		self.warn_children_over_18()

	# -- chuẩn hoá ---------------------------------------------------------

	def normalize_from_dates(self):
		"""Giảm trừ tính trọn tháng nên `from_date` luôn là ngày 01.

		Không ép `to_date`: kết thúc giữa tháng vẫn được trừ hết tháng đó, nên so sánh
		`to_date >= as_on` là đủ.
		"""
		for row in self.dependents:
			if row.from_date:
				row.from_date = get_first_day(row.from_date)

	# -- kiểm tra ----------------------------------------------------------

	def validate_periods(self):
		for row in self.dependents:
			if row.to_date and getdate(row.to_date) < getdate(row.from_date):
				frappe.throw(
					_("Dòng {0}: To Date không được trước From Date.").format(row.idx)
				)

	def validate_no_overlap_within_record(self):
		"""Cùng một NPT không được có hai khoảng thời gian chồng nhau trong cùng hồ sơ.

		Hai dòng cho một người là hợp lệ (vd ngừng rồi khai lại), miễn không chồng nhau.
		"""
		seen = {}
		for row in self.dependents:
			for other in seen.get(row.id_number, []):
				if _overlaps(row.from_date, row.to_date, other.from_date, other.to_date):
					frappe.throw(
						_("Dòng {0} và dòng {1} khai cùng một người phụ thuộc ({2}) "
						  "ở khoảng thời gian chồng lấn.").format(
							other.idx, row.idx, frappe.bold(row.dependent_name)
						),
						title=_("Trùng khoảng thời gian"),
					)
			seen.setdefault(row.id_number, []).append(row)

	def validate_not_claimed_by_other_employee(self):
		"""🔴 Nguyên tắc chống trùng — kiểm tra GIỮA CÁC NHÂN VIÊN.

		Luật: mỗi NPT chỉ được tính cho 01 người nộp thuế trong cùng **năm tính thuế**.
		Nên so trùng theo **năm dương lịch có giao nhau**, không phải theo khoảng ngày:
		hai anh em cùng khai một người mẹ, một người từ 01/2026 và một người từ 07/2026,
		là vi phạm dù khoảng ngày không chồng nhau.

		Đây là lý do ERP vẫn giữ `id_number` dù phần khai báo thuế nằm ở phần mềm khác:
		nhà máy có nhiều gia đình cùng làm, khai trùng làm sai **tiền lương thật**.
		"""
		my_tax_code = frappe.db.get_value("Employee", self.employee, "custom_tax_code")

		for row in self.dependents:
			if not row.id_number:
				continue
			my_years = _tax_years(row.from_date, row.to_date)

			for other in self._claims_elsewhere(row.id_number):
				# Tái tuyển: NLĐ nghỉ rồi vào lại được tạo hồ sơ Employee MỚI, nên cùng
				# một người có thể có 2 mã NV. Cùng MST = cùng người nộp thuế, không
				# phải khai trùng. Chỉ nhận diện được nhờ MST vì hai hồ sơ khác `name`.
				if my_tax_code and my_tax_code == frappe.db.get_value(
					"Employee", other.employee, "custom_tax_code"
				):
					continue

				shared = my_years & _tax_years(other.from_date, other.to_date)
				if shared:
					frappe.throw(
						_("Dòng {0}: số định danh {1} đã được nhân viên {2} khai cho năm "
						  "tính thuế {3} ({4}).<br><br>"
						  "Mỗi người phụ thuộc chỉ được tính giảm trừ cho <b>một</b> người "
						  "nộp thuế trong cùng năm tính thuế.").format(
							row.idx,
							frappe.bold(row.id_number),
							frappe.bold(other.employee),
							", ".join(str(y) for y in sorted(shared)),
							get_link_to_form("Employee Dependent", other.employee),
						),
						title=_("Người phụ thuộc đã được khai ở nơi khác"),
					)

	# -- cảnh báo (không chặn) --------------------------------------------

	def warn_children_over_18(self):
		"""Con từ 18 tuổi chỉ được tính NPT nếu khuyết tật hoặc đang học.

		Cảnh báo chứ không chặn: điều kiện "đang học"/"khuyết tật" nằm ở hồ sơ giấy và
		phần mềm kê khai thuế của HR, ERP không lưu. Mục đích duy nhất của cảnh báo này
		là chặn lỗi **payroll**: quên đặt `to_date` khi con hết tuổi ⇒ trừ thừa
		4.400.000đ/tháng mãi mãi.
		"""
		overdue = []
		for row in self.dependents:
			if row.relationship != "Child" or not row.date_of_birth or row.to_date:
				continue
			if _add_years(getdate(row.date_of_birth), 18) <= getdate(row.from_date):
				overdue.append(f"{row.idx}. {row.dependent_name}")

		if overdue:
			frappe.msgprint(
				_("Đã đủ 18 tuổi mà chưa có To Date: {0}.<br><br>"
				  "Chỉ được tính người phụ thuộc nếu <b>khuyết tật không có khả năng lao "
				  "động</b>, hoặc <b>đang học</b> và thu nhập bình quân ≤ 1.000.000đ/tháng. "
				  "Nếu không, hãy đặt To Date để dừng giảm trừ.").format(
					", ".join(overdue)
				),
				title=_("Kiểm tra điều kiện"),
				indicator="orange",
			)

	# -- nội bộ ------------------------------------------------------------

	def _claims_elsewhere(self, id_number: str) -> list:
		"""Các dòng cùng `id_number` nằm trong hồ sơ của nhân viên KHÁC.

		`parent` của child table chính là mã nhân viên (`autoname = field:employee`).
		"""
		Item = frappe.qb.DocType("Employee Dependent Item")
		rows = (
			frappe.qb.from_(Item)
			.select(Item.parent, Item.from_date, Item.to_date)
			.where(Item.parenttype == "Employee Dependent")
			.where(Item.id_number == id_number)
			.where(Item.parent != self.name)
			.orderby(Item.from_date)
		).run(as_dict=True)
		for r in rows:
			r.employee = r.parent
		return rows


# ---------------------------------------------------------------------------
# Tiện ích thời gian
# ---------------------------------------------------------------------------


def _add_years(d, years: int):
	"""Cộng năm, an toàn với 29/02 (lùi về 28/02)."""
	try:
		return d.replace(year=d.year + years)
	except ValueError:
		return d.replace(year=d.year + years, month=2, day=28)


def _overlaps(a_from, a_to, b_from, b_to) -> bool:
	a_from, b_from = getdate(a_from), getdate(b_from)
	a_to = getdate(a_to) if a_to else None
	b_to = getdate(b_to) if b_to else None
	if a_to and a_to < b_from:
		return False
	if b_to and b_to < a_from:
		return False
	return True


def _tax_years(from_date, to_date) -> set:
	"""Tập năm tính thuế mà khoảng [from_date, to_date] chạm tới.

	`to_date` trống = còn hiệu lực -> lấy tới hết năm sau, đủ để phát hiện trùng khi
	khai mới. Không lấy vô hạn vì sẽ chặn oan các năm xa trong tương lai.
	"""
	start = getdate(from_date).year
	end = getdate(to_date).year if to_date else getdate(frappe.utils.nowdate()).year + 1
	return set(range(start, max(start, end) + 1))


# ---------------------------------------------------------------------------
# API cho payroll
# ---------------------------------------------------------------------------


# Ngày "vô cực" thay cho `to_date` trống. Dùng Coalesce trong SQL thay vì OR hai nhánh —
# `get_all(filters=...)` của v16 không nhận biểu thức `ifnull(...)` làm fieldname.
_OPEN_ENDED = "3999-12-31"


def _effective_query(employee: str, as_on):
	"""Query các dòng NPT còn hiệu lực tại `as_on` (chưa select field nào).

	`parent` = mã nhân viên, nên không cần join sang doctype cha.
	"""
	as_on = getdate(as_on)
	Item = frappe.qb.DocType("Employee Dependent Item")
	return (
		frappe.qb.from_(Item)
		.where(Item.parenttype == "Employee Dependent")
		.where(Item.parent == employee)
		.where(Item.from_date <= as_on)
		.where(Coalesce(Item.to_date, _OPEN_ENDED) >= as_on)
		.orderby(Item.from_date)
	), Item


def get_dependent_count(employee: str, as_on) -> int:
	"""Số người phụ thuộc còn hiệu lực của `employee` tại ngày `as_on`.

	⚠ `as_on` phải là **`end_date` của Salary Slip**. Kỳ lương 26/06 -> 25/07 là
	tháng 7; truyền `start_date` sẽ ra tháng 6 — lệch đúng một tháng và rất khó phát
	hiện vì phần lớn nhân viên có thuế = 0.
	"""
	q, Item = _effective_query(employee, as_on)
	return len(q.select(Item.name).run())


@frappe.whitelist()
def get_dependents(employee: str, as_on: str | None = None) -> list:
	"""Danh sách NPT còn hiệu lực — dùng cho dashboard/report và kiểm tra bằng mắt."""
	frappe.has_permission("Employee Dependent", throw=True)
	q, Item = _effective_query(employee, as_on or frappe.utils.nowdate())
	return q.select(
		Item.name, Item.dependent_name, Item.relationship, Item.date_of_birth,
		Item.id_number, Item.from_date, Item.to_date,
	).run(as_dict=True)
