# Copyright (c) 2026, IT Team - TIQN and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


def _new_doc(**kwargs):
	"""Build an unsaved Health Check-Up doc for unit-testing controller methods."""
	doc = frappe.new_doc("Health Check-Up")
	doc.update(kwargs)
	return doc


class IntegrationTestHealthCheckUp(IntegrationTestCase):
	"""
	Integration tests for HealthCheckUp.
	Use this class for testing interactions between multiple components.
	"""

	# ---- compute_status ----

	def test_status_not_started(self):
		doc = _new_doc()
		doc.compute_status()
		self.assertEqual(doc.status, "Chưa khám")

	def test_status_in_exam(self):
		doc = _new_doc(start_time_actual="08:00:00")
		doc.compute_status()
		self.assertEqual(doc.status, "Đang khám")

	def test_status_completed(self):
		doc = _new_doc(start_time_actual="08:00:00", end_time_actual="09:30:00")
		doc.compute_status()
		self.assertEqual(doc.status, "Hoàn thành")

	def test_status_completed_even_without_start(self):
		# end_time_actual alone wins (imported/legacy data)
		doc = _new_doc(end_time_actual="09:30:00")
		doc.compute_status()
		self.assertEqual(doc.status, "Hoàn thành")

	# ---- validate_times ----

	def test_planned_end_must_be_after_start(self):
		doc = _new_doc(start_time="09:00:00", end_time="08:00:00")
		self.assertRaises(frappe.ValidationError, doc.validate_times)

	def test_actual_end_cannot_be_before_actual_start(self):
		doc = _new_doc(start_time_actual="10:00:00", end_time_actual="09:59:00")
		self.assertRaises(frappe.ValidationError, doc.validate_times)

	def test_times_compare_numerically_not_as_string(self):
		# "9:00" > "10:00" as string — get_time() must be used so this passes
		doc = _new_doc(start_time="9:00:00", end_time="10:00:00")
		doc.validate_times()  # must not raise

		doc = _new_doc(start_time_actual="9:00:00", end_time_actual="10:00:00")
		doc.validate_times()  # must not raise

	def test_actual_start_equals_end_is_allowed(self):
		# Scan phát và thu trong cùng 1 phút — hợp lệ
		doc = _new_doc(start_time_actual="08:00:00", end_time_actual="08:00:00")
		doc.validate_times()  # must not raise

	# ---- pregnant auto-check ----

	def test_pregnant_reset_for_male(self):
		doc = _new_doc(gender="Male", pregnant=1)
		doc.check_pregnant_status()
		self.assertEqual(doc.pregnant, 0)
