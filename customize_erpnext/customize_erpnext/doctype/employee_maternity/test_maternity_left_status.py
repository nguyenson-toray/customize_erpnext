"""Status `Left` + field `relieving_date` (plan employee_maternity_left_status.md, 09/11/2026).

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    import customize_erpnext.overrides
    exec(open('../apps/customize_erpnext/customize_erpnext/customize_erpnext/doctype/employee_maternity/test_maternity_left_status.py').read())"

CHỈ ĐỌC: doc dựng bằng `frappe.new_doc`, không lưu; `employment` truyền tay nên không query Employee.
"""

import unittest
from datetime import date, timedelta

import frappe

from customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_status_sync import (
	PHASE_INDICATOR,
	PHASE_PRIORITY,
)

TODAY = date.today()


def _doc(**dates):
	doc = frappe.new_doc("Employee Maternity")
	doc.employee = "TEST-EMP"
	for k, v in dates.items():
		doc.set(k, v)
	return doc


def _in_young_child():
	return _doc(
		pregnant_from_date=TODAY - timedelta(days=400),
		pregnant_to_date=TODAY - timedelta(days=200),
		maternity_from_date=TODAY - timedelta(days=199),
		maternity_to_date=TODAY - timedelta(days=20),
		youg_child_from_date=TODAY - timedelta(days=19),
		youg_child_to_date=TODAY + timedelta(days=100),
	)


def _finished_cycle():
	return _doc(
		pregnant_from_date=TODAY - timedelta(days=800),
		pregnant_to_date=TODAY - timedelta(days=600),
		maternity_from_date=TODAY - timedelta(days=599),
		maternity_to_date=TODAY - timedelta(days=420),
		youg_child_from_date=TODAY - timedelta(days=419),
		youg_child_to_date=TODAY - timedelta(days=50),
	)


class TestMaternityLeftStatus(unittest.TestCase):
	def test_left_mid_cycle(self):
		doc = _in_young_child()
		doc.calculate_status(employment={"relieving_date": TODAY - timedelta(days=1), "status": "Left"})
		self.assertEqual(doc.status, "Left")

	def test_left_on_relieving_day(self):
		# relieving_date = ngày ĐẦU TIÊN nghỉ → hôm nay đã là Left
		doc = _in_young_child()
		doc.calculate_status(employment={"relieving_date": TODAY, "status": "Active"})
		self.assertEqual(doc.status, "Left")

	def test_future_relieving_still_in_phase(self):
		doc = _in_young_child()
		doc.calculate_status(employment={"relieving_date": TODAY + timedelta(days=1), "status": "Active"})
		self.assertEqual(doc.status, "Young Child")

	def test_finished_then_left_is_left(self):
		# Phương án A: hồ sơ đã hết chu kỳ trước khi nghỉ việc cũng là Left
		doc = _finished_cycle()
		doc.calculate_status(employment={"relieving_date": TODAY - timedelta(days=10), "status": "Left"})
		self.assertEqual(doc.status, "Left")

	def test_finished_still_working_is_inactive(self):
		doc = _finished_cycle()
		doc.calculate_status(employment={"relieving_date": None, "status": "Active"})
		self.assertEqual(doc.status, "Inactive")

	def test_status_fallback_trailing_space(self):
		doc = _in_young_child()
		doc.calculate_status(employment={"relieving_date": None, "status": "Left "})
		self.assertEqual(doc.status, "Left")

	def test_relieving_date_mirrored(self):
		rd = TODAY + timedelta(days=5)
		doc = _in_young_child()
		emp = {"relieving_date": rd, "status": "Active"}
		doc.calculate_status(employment=emp)
		doc.calculate_derived_metrics(employment=emp)
		self.assertEqual(doc.relieving_date, rd)

	def test_relieving_date_cleared_on_rehire(self):
		doc = _in_young_child()
		doc.relieving_date = TODAY - timedelta(days=30)
		emp = {"relieving_date": None, "status": "Active"}
		doc.calculate_status(employment=emp)
		doc.calculate_derived_metrics(employment=emp)
		self.assertIsNone(doc.relieving_date)
		self.assertEqual(doc.status, "Young Child")

	def test_left_has_no_overtime_status(self):
		doc = _in_young_child()
		emp = {"relieving_date": TODAY - timedelta(days=1), "status": "Left"}
		doc.calculate_status(employment=emp)
		doc.calculate_derived_metrics(employment=emp)
		self.assertFalse(doc.overtime_status)

	def test_colors_and_priority(self):
		self.assertEqual(PHASE_INDICATOR["Left"], "red")
		self.assertGreater(PHASE_PRIORITY["Left"], PHASE_PRIORITY["Inactive"])

	def test_status_option_exists(self):
		options = frappe.get_meta("Employee Maternity").get_field("status").options.split("\n")
		self.assertIn("Left", options)
		self.assertTrue(frappe.get_meta("Employee Maternity").has_field("relieving_date"))


unittest.TextTestRunner(verbosity=2).run(
	unittest.defaultTestLoader.loadTestsFromTestCase(TestMaternityLeftStatus)
)
