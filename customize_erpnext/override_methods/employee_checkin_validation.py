# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate


def validate_employee_checkin_for_left_employee(doc, method=None):
	"""
	Validate that Employee Checkin cannot be created after employee's relieving date
	for employees with status = "Left"

	This validation ensures consistency with Daily Timesheet validation
	"""
	if not doc.employee or not doc.time:
		return

	# Get employee status and relieving_date
	employee_data = frappe.db.get_value(
		"Employee",
		doc.employee,
		["status", "relieving_date"],
		as_dict=1
	)

	if not employee_data:
		return

	# Check if employee has Left status and has relieving_date
	if employee_data.status == "Left" and employee_data.relieving_date:
		checkin_date = getdate(doc.time)
		relieving_date = getdate(employee_data.relieving_date)

		# Throw error if checkin date is after relieving date
		if checkin_date > relieving_date:
			frappe.throw(
				_("Cannot create Employee Checkin: Check-in date ({0}) is after employee's relieving date ({1}). Employee has Left status.").format(
					frappe.utils.formatdate(checkin_date),
					frappe.utils.formatdate(relieving_date)
				),
				title=_("Invalid Check-in Date")
			)
