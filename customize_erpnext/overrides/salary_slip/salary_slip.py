# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import erpnext
import frappe
from frappe import _
from frappe.utils import cint, flt, get_link_to_form, getdate

from customize_erpnext.customize_erpnext.doctype.tiqn_payroll_settings.tiqn_payroll_settings import (
	get_settings,
)
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from hrms.utils.holiday_list import get_holiday_dates_between, get_holiday_list_for_employee

HOLIDAYS_CACHE = "tiqn_payroll_weekly_offs"

# Giờ OT chốt để trả lương. KHÔNG dùng `custom_approved_overtime_duration` — đó là giờ
# đăng ký/duyệt. Ca thật TIQN-0047: approved = 66h nhưng final = 36,1h, và chỉ `final`
# mới khớp phiếu lương.
VND = "VND"
OT_SOURCE_FIELD = "custom_final_overtime_duration"

# Khoản trả một lần/năm — khớp theo tiền tố vì tên component có cả tiếng Anh lẫn tiếng Việt
MENSTRUAL_COMPONENT_PREFIX = "7.5"

# Hệ số OT theo BLĐ Đ.98 — giữ khớp với formula của Salary Structure (dòng 2.1/2.2/2.3)
OT_MULTIPLIER = {"normal": 1.5, "weekend": 2.0, "holiday": 3.0}
STANDARD_HOURS_PER_DAY = 8


class CustomSalarySlip(SalarySlip):
	def autoname(self):
		"""`Sal Slip/{mã NV}/{YYYYMM}` thay cho số thứ tự chạy `Sal Slip/{mã NV}/00001`.

		Số thứ tự không nói lên kỳ nào — với 1000 nhân viên × 12 kỳ/năm thì tra cứu và đối
		chiếu rất khó. Tên có kỳ lương thì đọc là biết ngay.

		Tháng lấy từ **`end_date`**: kỳ 26/06 → 25/07 là **tháng 7** (202607). Dùng
		`start_date` sẽ ra tháng 6 — cùng quy ước với việc đếm người phụ thuộc và tra
		tham số theo ngày hiệu lực.
		"""
		if not (self.employee and self.end_date):
			return super().autoname()

		base = f"Sal Slip/{self.employee}/{getdate(self.end_date).strftime('%Y%m')}"
		self.name = base

		# Phiếu đã HUỶ vẫn giữ tên và không bị `check_existing()` chặn, nên vẫn có thể
		# đụng tên khi lập lại phiếu cho cùng kỳ.
		suffix = 1
		while frappe.db.exists("Salary Slip", self.name):
			self.name = f"{base}-{suffix}"
			suffix += 1

	def validate(self):
		super().validate()
		self.set_salary_month()
		self.warn_incomplete_attendance()
		self.warn_annual_allowance_in_wrong_period()

	def set_net_total_in_words(self):
		"""Số tiền bằng chữ **tiếng Việt** cho phiếu lương VNĐ.

		HRMS gọi `frappe.utils.money_in_words()` (`hrms/salary_slip.py:197`) — hàm đó trả về
		**tiếng Anh** (*"Seventeen Million ... Dong only"*), không dùng được cho chứng từ trả
		lương tại Việt Nam.

		Chỉ đổi khi đồng tiền là **VND**; đồng tiền khác vẫn để HRMS xử lý như cũ.

		Hàm dùng: `api/vn_number_words.money_in_words_vi()` — thuần stdlib, không import
		`frappe`, nên `tests/test_vn_number_words.py` chạy được không cần bench/site.
		"""
		super().set_net_total_in_words()

		from customize_erpnext.api.vn_number_words import money_in_words_vi

		total = self.net_pay if self.is_rounding_total_disabled() else self.rounded_total
		base_total = (
			self.base_net_pay if self.is_rounding_total_disabled() else self.base_rounded_total
		)
		# flt(): `money_in_words_vi(None)` trả về chuỗi RỖNG, không lỗi — để nguyên thì
		# field bằng chữ im lặng trống. flt(None) = 0.0 -> "Không đồng".
		if self.currency == VND:
			self.total_in_words = money_in_words_vi(flt(total))
		if erpnext.get_company_currency(self.company) == VND:
			self.base_total_in_words = money_in_words_vi(flt(base_total))

	def set_salary_month(self):
		"""`custom_salary_month` — kỳ lương này là tháng nào, dạng `Jul-2026`.

		Lấy theo **`end_date`**, cùng quy ước với `autoname()`: kỳ 26/06 → 25/07 là **tháng 7**.
		Dùng `start_date` sẽ ra tháng 6 — lệch đúng một tháng và rất khó phát hiện.

		Field này để lọc/nhóm báo cáo cho dễ; `start_date`/`end_date` vẫn là nguồn thật.
		"""
		if not self.end_date:
			return
		self.custom_salary_month = getdate(self.end_date).strftime("%b-%Y")

	def warn_incomplete_attendance(self):
		"""🔴 Cảnh báo ngày chấm công THIẾU LƯỢT QUẸT trong kỳ — HR phải rà trước khi chốt lương.

		Ngày chỉ có lượt quẹt vào (không có lượt ra hợp lệ) được tính `Present` với
		`working_hours = 0` — xem `overrides/shift_type/OPTIMIZATION_GUIDE.md`. Đó là chủ ý:
		người lao động **đã đến làm**, để `Absent` là cắt trọn ngày lương của họ.

		Nhưng cái giá là **trả đủ ngày mà không có giờ nào ghi nhận**, và giờ OT của ngày đó
		cũng bằng 0 vì không có mốc kết thúc. Vì vậy quy trình bắt buộc: **HR rà soát và bổ
		sung lượt quẹt thiếu TRƯỚC khi tính lương**, không để hệ thống tự đoán.

		Chỉ cảnh báo, không chặn — kỳ đang diễn ra thì thiếu lượt ra là bình thường (đo
		12/08/2026: 936/952 bản thuộc kỳ hiện tại, các kỳ đã đóng chỉ 1-4 bản mỗi kỳ).
		Chặn cứng sẽ làm không lập nổi phiếu nháp giữa kỳ.

		🔴 **Bỏ qua khi lập hàng loạt qua Payroll Entry.**
		`create_salary_slips_for_employees()` (`payroll_entry.py:1560`) gọi `insert()` cho
		TỪNG nhân viên và **không** mute message. Đo kỳ 26/07-25/08: **938** nhân viên có
		ngày thiếu lượt quẹt ⇒ 938 `msgprint` dồn vào `frappe.message_log` của một
		background job mà **không ai đọc** — chỉ tốn bộ nhớ.

		Đường chính để HR rà là **sheet "Important Note"** của report Shift Attendance
		Customize, chạy TRƯỚC khi tính lương (`payroll_docs/PAYROLL_SETUP.md` mục 4.10).
		Cảnh báo ở đây chỉ là lưới an toàn khi lập/sửa **một** phiếu bằng tay.
		"""
		if self.payroll_entry:
			return
		if not (self.employee and self.start_date and self.end_date):
			return

		Attendance = frappe.qb.DocType("Attendance")
		rows = (
			frappe.qb.from_(Attendance)
			.select(Attendance.name, Attendance.attendance_date, Attendance.custom_note)
			.where(
				(Attendance.employee == self.employee)
				& (Attendance.attendance_date.between(self.start_date, self.end_date))
				& (Attendance.docstatus == 1)
				& Attendance.in_time.isnotnull()
				& Attendance.out_time.isnull()
			)
			.orderby(Attendance.attendance_date)
		).run(as_dict=True)
		if not rows:
			return

		lines = "".join(
			"<li>{0} — {1}</li>".format(
				frappe.utils.formatdate(r.attendance_date),
				get_link_to_form("Attendance", r.name, label=_("open")),
			)
			for r in rows
		)
		frappe.msgprint(
			_("{0} day(s) in this period have a check-IN but no check-OUT, so they are paid "
			  "as a full day with 0 recorded hours (and 0 overtime).<br><br>"
			  "Please review and complete the missing check-ins before finalising payroll."
			  "<ul>{1}</ul>").format(len(rows), lines),
			title=_("Incomplete attendance"),
			indicator="orange",
		)

	def warn_annual_allowance_in_wrong_period(self):
		"""Cảnh báo khi khoản trả MỘT LẦN/NĂM lại xuất hiện ở kỳ lương khác.

		Quy chế mục 3: phụ cấp kinh nguyệt chi trả **một năm một lần cùng kỳ lương tháng 12**
		(hoặc khi lao động nữ thôi việc). Nhưng file lương thật của HR kỳ 07/2026 lại có
		khoản này ở **mọi tháng** — quy chế và thực tế đang mâu thuẫn
		(`overrides/payroll_docs/PAYROLL_SETUP.md` mục 6.2, N4).

		Cảnh báo chứ không chặn: trả khi thôi việc là hợp lệ ở bất kỳ tháng nào.
		"""
		month = cint(get_settings().menstrual_allowance_month)
		if not month or cint(getdate(self.end_date).month) == month:
			return

		rows = [r for r in self.earnings
		        if r.salary_component.startswith(MENSTRUAL_COMPONENT_PREFIX) and flt(r.amount)]
		if not rows:
			return

		frappe.msgprint(
			_("{0} chỉ trả một lần trong năm, vào kỳ lương <b>tháng {1}</b> theo quy chế. "
			  "Kỳ này là tháng {2} — chỉ hợp lệ nếu người lao động thôi việc.").format(
				frappe.bold(rows[0].salary_component), month, getdate(self.end_date).month),
			title=_("Khoản trả một lần/năm"),
			indicator="orange",
		)

	def calculate_net_pay(self, *args, **kwargs):
		"""Nạp giờ OT từ Attendance trước khi tính các dòng lương.

		Đặt ở đây vì `calculate_net_pay()` chạy sau khi ngày kỳ lương và Salary Structure
		Assignment đã được xác định (`salary_slip.py:162`), và là đường đi chung của cả
		phiếu lưu thật lẫn bản xem trước của `process_salary_structure`.
		"""
		self.set_ot_hours_from_attendance()
		return super().calculate_net_pay(*args, **kwargs)

	def set_ot_hours_from_attendance(self):
		"""Điền `custom_ot_*_hours` từ Attendance của kỳ lương.

		Phân loại 3 loại OT bằng chính Holiday List — không cần field phân loại riêng:
		    có trong list, `weekly_off = 1`  -> OT cuối tuần   (200%)
		    có trong list, `weekly_off = 0`  -> OT ngày lễ     (300%)
		    không có trong list              -> OT ngày thường (150%)

		Tick `custom_ot_override` để giữ số nhập tay — cần cho trường hợp HR điều chỉnh
		giờ OT trước khi trả lương (xem `overrides/payroll_docs/PAYROLL_SETUP.md` mục 2.4).
		"""
		if self.get("custom_ot_override"):
			return
		if not (self.employee and self.start_date and self.end_date):
			return

		hours = self._fetch_ot_hours()

		# LUÔN gán, kể cả 0 — nếu chỉ gán khi có phần vượt thì giá trị cũ nằm lại trong khi
		# giờ OT đã quay về đủ ⇒ **cộng trùng tiền**. Cùng loại bẫy với việc phải xoá dòng
		# cũ trước khi append trong `vn_deductions._upsert()`.
		self.custom_kpi_incentive = self._move_excess_ot_to_kpi(hours)
		self.custom_ot_normal_hours = hours["normal"]
		self.custom_ot_weekend_hours = hours["weekend"]
		self.custom_ot_holiday_hours = hours["holiday"]

	def _move_excess_ot_to_kpi(self, hours: dict) -> float:
		"""Chuyển giờ OT vượt **trần tháng** sang tiền KPI. Trả về số tiền (0 nếu không có).

		Vì sao cần: tiền OT **trong trần** được miễn thuế TNCN, phần **vượt trần** thì chịu
		thuế (NĐ 253/2026 Đ.26). Để chung một dòng OT là khai sai thuế.
		Đã đối chiếu phiếu thật `TIQN-0019` kỳ 07/2026: chấm công 55h → phiếu ghi OT 35h,
		phần còn lại nằm ở dòng `4.3 KPI`. Tổng tiền hai cách chênh nhau 537đ (0,017%) —
		chỉ do HR làm tròn từng phần.

		🔴 **Trần đếm theo THÁNG DƯƠNG LỊCH**, không theo kỳ lương: kỳ 26/06→25/07 chạm hai
		tháng, mỗi tháng có trần riêng (`PAYROLL_SETUP.md` mục 2.6).

		Thứ tự cắt: **ngày thường → cuối tuần → ngày lễ**. Giữ lại giờ có hệ số cao trong
		diện miễn thuế — có lợi cho người lao động, và luật chỉ giới hạn *số giờ*, không
		quy định cắt giờ nào.

		⚠ `custom_kpi_incentive` **do hệ thống quản lý** — bị ghi đè (kể cả về 0) mỗi lần tính
		lại. Muốn nhập KPI thủ công thì tick `custom_ot_override`, hoặc dùng `Additional Salary`.
		"""
		settings = get_settings()
		cap = flt(settings.ot_cap_per_month)
		if not (settings.move_excess_ot_to_kpi and cap):
			return 0.0

		excess_by_bucket = {"normal": 0.0, "weekend": 0.0, "holiday": 0.0}
		for month_hours in self._ot_hours_by_month().values():
			over = sum(month_hours.values()) - cap
			if over <= 0:
				continue
			# cắt từ hệ số thấp lên cao
			for bucket in ("normal", "weekend", "holiday"):
				take = min(over, month_hours[bucket])
				excess_by_bucket[bucket] += take
				over -= take
				if over <= 0:
					break

		if not any(excess_by_bucket.values()):
			return 0.0

		hourly = flt(self._ssa_si_base()) / (flt(self.total_working_days) * STANDARD_HOURS_PER_DAY or 1)
		amount = 0.0
		for bucket, multiplier in OT_MULTIPLIER.items():
			taken = excess_by_bucket[bucket]
			if not taken:
				continue
			hours[bucket] = max(0.0, hours[bucket] - taken)
			amount += hourly * taken * multiplier
		return flt(amount, 0)

	def _ssa_si_base(self) -> float:
		return flt(frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": self.employee, "salary_structure": self.salary_structure,
			 "from_date": ("<=", self.end_date), "docstatus": 1},
			"custom_si_base", order_by="from_date desc",
		))

	def _ot_hours_by_month(self) -> dict:
		"""`{(năm, tháng): {normal/weekend/holiday: giờ}}` — tách theo tháng dương lịch."""
		holidays = self._holiday_map(self.start_date, self.end_date)
		attendance = frappe.qb.DocType("Attendance")
		rows = (
			frappe.qb.from_(attendance)
			.select(attendance.attendance_date, attendance[OT_SOURCE_FIELD].as_("ot_hours"))
			.where(attendance.docstatus == 1)
			.where(attendance.employee == self.employee)
			.where(attendance.attendance_date >= self.start_date)
			.where(attendance.attendance_date <= self.end_date)
			.where(attendance[OT_SOURCE_FIELD] > 0)
		).run(as_dict=True)

		by_month = {}
		for row in rows:
			d = getdate(row.attendance_date)
			bucket = self._ot_bucket(holidays.get(d))
			by_month.setdefault((d.year, d.month),
			                    {"normal": 0.0, "weekend": 0.0, "holiday": 0.0})
			by_month[(d.year, d.month)][bucket] += flt(row.ot_hours)
		return by_month

	@staticmethod
	def _ot_bucket(weekly_off) -> str:
		if weekly_off is None:
			return "normal"
		return "weekend" if weekly_off else "holiday"

	def _fetch_ot_hours(self) -> dict:
		holidays = self._holiday_map(self.start_date, self.end_date)

		attendance = frappe.qb.DocType("Attendance")
		rows = (
			frappe.qb.from_(attendance)
			.select(attendance.attendance_date, attendance[OT_SOURCE_FIELD].as_("ot_hours"))
			.where(attendance.docstatus == 1)
			.where(attendance.employee == self.employee)
			.where(attendance.attendance_date >= self.start_date)
			.where(attendance.attendance_date <= self.end_date)
			.where(attendance[OT_SOURCE_FIELD] > 0)
		).run(as_dict=True)

		totals = {"normal": 0.0, "weekend": 0.0, "holiday": 0.0}
		for row in rows:
			totals[self._ot_bucket(holidays.get(getdate(row.attendance_date)))] += flt(row.ot_hours)
		return totals

	def _holiday_map(self, start_date, end_date) -> dict:
		"""`{ngày: weekly_off}` cho cả kỳ lương, từ **một** Holiday List.

		Dùng một list được vì `Holiday List` của TIQN đã khai trùng khít **năm lương**
		(26/12 năm trước → 25/12 năm sau), giống `Payroll Period`. Nhờ vậy không kỳ lương
		nào vắt qua ranh giới hai list.

		⚠ Tra list theo **`end_date` của kỳ**, không phải theo hôm nay. Mặc định của
		`get_holiday_list_for_employee()` là `as_on = today` — tính lại kỳ cũ hoặc lập
		trước kỳ tương lai sẽ lấy nhầm list của năm khác.

		> Khi tạo Holiday List năm mới, nhớ đặt phạm vi **26/12 → 25/12** cho khớp năm lương.
		"""
		holiday_list = get_holiday_list_for_employee(self.employee, as_on=end_date)
		key = f"{holiday_list}:{start_date}:{end_date}"

		cached = frappe.cache().hget(HOLIDAYS_CACHE, key)
		if cached is not None:
			return {getdate(d): wo for d, wo in cached}

		holidays = {
			getdate(row.holiday_date): (1 if row.weekly_off else 0)
			for row in get_holiday_dates_between(
				holiday_list, start_date, end_date, as_dict=True, select_weekly_off=True
			)
		}
		frappe.cache().hset(HOLIDAYS_CACHE, key, [(str(d), wo) for d, wo in holidays.items()])
		return holidays

	def get_holidays_for_employee(self, start_date, end_date):
		"""Chỉ trả về CHỦ NHẬT (`weekly_off = 1`), bỏ qua ngày lễ nhà nước.

		Quy tắc TIQN: ngày công chuẩn = số ngày trong kỳ lương − số Chủ Nhật.
		**Ngày lễ theo quy định nhà nước VẪN TÍNH công và trả lương** dù không đi
		làm, nên KHÔNG được trừ khỏi `total_working_days`.

		Bản gốc của HRMS trừ TẤT CẢ dòng trong Holiday List (cả Chủ Nhật lẫn ngày
		lễ) — với kỳ Tết 26/01→25/02/2026 sẽ ra 18 ngày công thay vì 27, làm đơn
		giá ngày (base / total_working_days) sai hoàn toàn.

		Holiday List vẫn khai đủ cả hai loại để chấm công / nghỉ phép dùng chung;
		hai loại phân biệt bằng cờ `Holiday.weekly_off`.
		"""
		return [d for d, weekly_off in self._holiday_map(start_date, end_date).items() if weekly_off]

	def all_holidays_in_period(self) -> list:
		"""TẤT CẢ ngày nghỉ của kỳ — Chủ Nhật **và** ngày lễ nhà nước."""
		return list(self._holiday_map(self.start_date, self.end_date).keys())

	# ------------------------------------------------------------------
	# 🔴 HRMS dùng MỘT danh sách `holidays` cho hai mục đích trái nhau
	# ------------------------------------------------------------------
	# `get_working_days_details()` (hrms salary_slip.py:497) lấy `holidays` một lần rồi
	# truyền đi khắp nơi:
	#
	#   (a) `working_days -= len(holidays)`   -> ngày công chuẩn: CHỈ được trừ Chủ Nhật
	#   (b) bỏ qua Absent rơi vào ngày nghỉ   -> phải tính CẢ ngày lễ
	#
	# `get_holidays_for_employee()` ở trên phục vụ (a). Nếu để nguyên thì (b) không thấy
	# ngày lễ, nên một bản ghi Attendance `Absent` rơi vào ngày lễ sẽ **trừ lương thật**.
	#
	# Đo được trên `Sal Slip/TIQN-0148/202602` (kỳ Tết 26/01→25/02/2026): 9 ngày Tết bị
	# chấm Absent -> payment_days 18/27 thay vì 27/27, mất 9 ngày lương.
	# Quy chế: ngày lễ nhà nước **vẫn tính công và trả lương**.
	#
	# Hai hàm dưới đây thay `holidays` bằng danh sách đầy đủ cho đúng mục đích (b).
	# KHÔNG đụng `get_unmarked_days()`: nó đếm ngày "chưa chấm công", cần danh sách
	# Chủ Nhật thôi — đưa cả ngày lễ vào sẽ loại 9 bản ghi Tết khỏi nhóm "đã chấm"
	# rồi tính chúng thành vắng mặt lần nữa.

	def calculate_lwp_ppl_and_absent_days_based_on_attendance(
		self, holidays, daily_wages_fraction_for_half_day, consider_marked_attendance_on_holidays
	):
		return super().calculate_lwp_ppl_and_absent_days_based_on_attendance(
			self.all_holidays_in_period(),
			daily_wages_fraction_for_half_day,
			consider_marked_attendance_on_holidays,
		)

	def get_half_absent_days(self, consider_marked_attendance_on_holidays, holidays):
		return super().get_half_absent_days(
			consider_marked_attendance_on_holidays, self.all_holidays_in_period()
		)
