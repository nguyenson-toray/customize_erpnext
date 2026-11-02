"""Test thuần (không đụng DB) cho chế độ Period + quy tắc leave_months.

bench --site erp.tiqn.local run-tests --module customize_erpnext.customize_erpnext.report.employee_maternity_report.test_employee_maternity_period
"""

import unittest

import frappe
from frappe.utils import getdate

from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity import (
	maternity_end_date,
	overtime_status,
	seventh_month_date,
	whole_leave_months,
)
from customize_erpnext.customize_erpnext.report.employee_maternity_report.employee_maternity_report import (
	_in_period,
	_left_during,
	_left_record_by_employee,
)

D = getdate


def rec(**kw):
	base = dict(
		maternity_record="R1", employee="E1", employee_status="Left", relieving_date=None,
		pregnant_from_date=None, pregnant_to_date=None, mat_from=None, maternity_to_date=None,
		youg_child_from_date=None, youg_child_to_date=None,
	)
	base.update(kw)
	return frappe._dict(base)


class TestLeaveMonths(unittest.TestCase):
	def test_end_date(self):
		self.assertEqual(maternity_end_date("2026-01-19", 6), D("2026-07-18"))
		self.assertEqual(maternity_end_date("2026-01-19", 7), D("2026-08-18"))
		# cuối tháng: 31/08 + 6 tháng = 28/02 (năm thường) - 1 = 27/02
		self.assertEqual(maternity_end_date("2026-08-31", 6), D("2027-02-27"))

	def test_whole_months_roundtrip(self):
		for start in ["2026-01-19", "2026-08-31", "2024-02-29", "2026-12-01"]:
			for n in (4, 6, 7, 9):
				self.assertEqual(whole_leave_months(start, maternity_end_date(start, n)), n, (start, n))

	def test_whole_months_irregular_is_zero(self):
		# dữ liệu cũ "6 tháng 1 ngày" (trước khi sửa -1 ngày) → 0, giữ ngày HR nhập
		self.assertEqual(whole_leave_months("2026-01-20", "2026-07-20"), 0)
		self.assertEqual(whole_leave_months(None, "2026-07-20"), 0)


class TestPeriod(unittest.TestCase):
	F, T = D("2026-03-01"), D("2026-03-31")

	def test_overlap(self):
		self.assertTrue(_in_period("2026-01-01", "2026-03-01", self.F, self.T))  # chạm ngày đầu
		self.assertTrue(_in_period("2026-03-31", "2026-09-01", self.F, self.T))  # chạm ngày cuối
		self.assertTrue(_in_period("2026-01-01", None, self.F, self.T))  # to trống = đang diễn ra
		self.assertFalse(_in_period("2026-01-01", "2026-02-28", self.F, self.T))
		self.assertFalse(_in_period(None, None, self.F, self.T))

	def test_single_day_period(self):
		day = D("2026-03-10")
		self.assertTrue(_in_period("2026-03-10", "2026-03-10", day, day))

	def test_phase_cut_at_relieving_date(self):
		# nghỉ việc từ 01/03 → ngày làm/chế độ cuối là 28/02 → không còn trong kỳ tháng 3
		self.assertFalse(_in_period("2026-01-01", "2026-06-30", self.F, self.T, D("2026-03-01")))
		self.assertTrue(_in_period("2026-01-01", "2026-06-30", self.F, self.T, D("2026-03-02")))
		self.assertFalse(_in_period("2026-04-01", None, self.F, self.T, D("2026-03-15")))

	def test_left_during(self):
		r = rec(pregnant_from_date=D("2026-01-01"), pregnant_to_date=D("2026-05-31"),
			mat_from=D("2026-06-01"), maternity_to_date=D("2026-11-30"),
			youg_child_from_date=D("2026-12-01"), youg_child_to_date=D("2027-05-01"))
		cases = {
			"2025-12-01": "Before Pregnancy", "2026-03-01": "Pregnant", "2026-06-01": "Maternity Leave",
			"2026-11-30": "Maternity Leave", "2026-12-01": "Did Not Return",
			"2026-12-02": "Young Child", "2027-06-01": "After Young Child Period",
		}
		for day, expected in cases.items():
			r.relieving_date = D(day)
			self.assertEqual(_left_during(r), expected, day)

	def test_left_assigned_to_latest_cycle_only(self):
		records = [
			rec(maternity_record="OLD", pregnant_from_date=D("2023-01-01"), relieving_date=D("2026-05-01")),
			rec(maternity_record="NEW", pregnant_from_date=D("2025-06-01"), relieving_date=D("2026-05-01")),
			rec(maternity_record="LATER", pregnant_from_date=D("2026-09-01"), relieving_date=D("2026-05-01")),
		]
		self.assertEqual(_left_record_by_employee(records), {"E1": "NEW"})

	def test_left_requires_status_left(self):
		records = [rec(employee_status="Active", relieving_date=D("2026-05-01"), pregnant_from_date=D("2026-01-01"))]
		self.assertEqual(_left_record_by_employee(records), {})
		# status "Left " có dấu cách (1.393 bản ghi trên site) vẫn phải nhận
		records[0].employee_status = "Left "
		self.assertEqual(_left_record_by_employee(records), {"E1": "R1"})


class TestSeventhMonthOvertime(unittest.TestCase):
	"""Tháng thứ 7 = EDATE(Ngày dự sinh; -3); Overtime CHỈ tính trong giai đoạn Mang thai."""

	def test_seventh_month_date(self):
		self.assertEqual(seventh_month_date("2027-03-15"), D("2026-12-15"))
		self.assertEqual(seventh_month_date("2027-05-31"), D("2027-02-28"))  # kẹp cuối tháng như EDATE
		self.assertIsNone(seventh_month_date(None))

	def ot(self, on, has_left=False, **kw):
		args = dict(estimated_due_date="2027-03-15", pregnant_from_date="2026-08-01",
			pregnant_to_date="2027-03-14")
		args.update(kw)
		return overtime_status(**args, on_date=on, has_left=has_left)

	def test_boundary(self):
		self.assertEqual(self.ot("2026-12-14"), "Allowed")
		self.assertEqual(self.ot("2026-12-15"), "Not Allowed")  # đúng ngày bắt đầu tháng 7
		self.assertEqual(self.ot("2027-03-14"), "Not Allowed")  # ngày cuối Mang thai

	def test_outside_pregnant_is_blank(self):
		self.assertIsNone(self.ot("2026-07-31"))  # chưa mang thai
		self.assertIsNone(self.ot("2027-03-15"))  # đã sang nghỉ thai sản
		self.assertIsNone(self.ot("2027-12-01"))  # con nhỏ

	def test_pregnant_to_empty_uses_due_date(self):
		self.assertEqual(self.ot("2027-03-15", pregnant_to_date=None), "Not Allowed")
		self.assertIsNone(self.ot("2027-03-16", pregnant_to_date=None))

	def test_miscarriage(self):
		self.assertEqual(self.ot("2027-01-10", pregnant_to_date="2027-01-10"), "Not Allowed")
		self.assertIsNone(self.ot("2027-01-11", pregnant_to_date="2027-01-10"))

	def test_blank(self):
		self.assertIsNone(self.ot("2026-12-20", estimated_due_date=None))
		self.assertIsNone(self.ot("2026-12-20", has_left=True))
		self.assertIsNone(self.ot("2026-12-20", pregnant_from_date=None))
