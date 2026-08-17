# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Holiday reminder email — greet people by their full name.

HRMS greets with `first_name`. In a Vietnamese name the first word is the family
name, so the stock greeting addresses everyone by their surname: "Hey Nguyễn!"
reads roughly like "Hey Smith!". Worse, `first_name` is now a hidden derived
field here — Full Name is the only name anybody maintains.

Same function as HRMS otherwise; only the greeting line differs.
"""

import frappe
from frappe import _

from erpnext.setup.doctype.employee.employee import get_employee_email

from hrms.controllers.employee_reminders import get_sender_email


def custom_send_holidays_reminder_in_advance(employee, holidays):
	if not holidays:
		return

	employee_doc = frappe.get_doc("Employee", employee)
	employee_email = get_employee_email(employee_doc)
	frequency = frappe.db.get_single_value("HR Settings", "frequency")
	sender_email = get_sender_email()
	email_header = _("Holidays this Month.") if frequency == "Monthly" else _("Holidays this Week.")

	# The only change from HRMS: employee_name instead of first_name.
	greeting_name = employee_doc.get("employee_name") or employee_doc.get("first_name") or ""

	frappe.sendmail(
		sender=sender_email,
		recipients=[employee_email],
		subject=_("Upcoming Holidays Reminder"),
		template="holiday_reminder",
		args=dict(
			reminder_text=_("Hey {}! This email is to remind you about the upcoming holidays.").format(
				greeting_name
			),
			message=_("Below is the list of upcoming holidays for you:"),
			advance_holiday_reminder=True,
			holidays=holidays,
			frequency=frequency[:-2],
		),
		header=email_header,
	)
