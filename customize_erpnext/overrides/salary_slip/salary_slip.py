# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from hrms.payroll.doctype.salary_slip.salary_slip import SalarySlip
from hrms.utils.holiday_list import get_holiday_dates_between, get_holiday_list_for_employee

HOLIDAYS_CACHE = "tiqn_payroll_weekly_offs"


class CustomSalarySlip(SalarySlip):
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
		holiday_list = get_holiday_list_for_employee(self.employee)
		key = f"{holiday_list}:{start_date}:{end_date}"

		dates = frappe.cache().hget(HOLIDAYS_CACHE, key)
		if dates is None:
			rows = get_holiday_dates_between(
				holiday_list, start_date, end_date, as_dict=True, select_weekly_off=True
			)
			dates = [r.holiday_date for r in rows if r.weekly_off]
			frappe.cache().hset(HOLIDAYS_CACHE, key, dates)

		return dates
