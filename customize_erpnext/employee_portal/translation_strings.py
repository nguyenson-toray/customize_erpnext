# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Strings the portal translates through a VARIABLE: `_(label, context="Portal")`,
`notify(..., "has been published")`, Holiday List descriptions from the DB...

String extraction (bench generate-pot-file, scripts.vi_po.build / add_new_strings)
only sees literal `_("...")` calls, so these were dropped from locale/vi.po on
21/10/2026 and the Mini App showed English. Listing them here as literals keeps them
in vi.po. Never called. Add a line whenever a new string is translated via a variable.
"""

from frappe import _


def _strings():  # pragma: no cover - extraction only
	_("has been published")
	_("Earnings", context="Payslip")
	_("Deductions", context="Payslip")
	_("Adjustment for Previous Month")
	_("Attendance & Overtime")
	_("Monday", context="Portal")
	_("Tuesday", context="Portal")
	_("Wednesday", context="Portal")
	_("Thursday", context="Portal")
	_("Friday", context="Portal")
	_("Saturday", context="Portal")
	_("Sunday", context="Portal")
	_("Mon", context="Portal")
	_("Tue", context="Portal")
	_("Wed", context="Portal")
	_("Thu", context="Portal")
	_("Fri", context="Portal")
	_("Sat", context="Portal")
	_("Sun", context="Portal")
	_("{0} h {1:02d}", context="Portal")
	_("{0} h", context="Portal")
	_("Office Hours", context="Portal")
	_("Late / Left Early", context="Portal")
	_("On Leave", context="Portal")
	_("Absent", context="Portal")
	_("Not Checked In", context="Portal")
	_("Working", context="Portal")
	_("Checked Out", context="Portal")
	_("Holiday", context="Portal")
	_("Day Off", context="Portal")
	_("Pending Approval", context="Portal")
	_("Approved", context="Portal")
	_("Rejected", context="Portal")
	_("Cancelled", context="Portal")
	_("Registered", context="Portal")
	_("Business trip / working outside", context="Portal")
	_("Working remotely", context="Portal")
	_("Forgot to check in/out", context="Portal")
	_("Attendance machine error", context="Portal")
	_("First working day", context="Portal")
	_("Other reason", context="Portal")
	_("New Year's Day", context="Portal")
	_("Lunar New Year's Eve", context="Portal")
	_("Lunar New Year", context="Portal")
	_("Second Day of Lunar New Year", context="Portal")
	_("Third Day of Lunar New Year", context="Portal")
	_("Fourth Day of Lunar New Year", context="Portal")
	_("Lunar New Year-bonus", context="Portal")
	_("Liberation Day/Reunification Day", context="Portal")
	_("International Labor Day", context="Portal")
	_("Hung Kings' Commemoration Day (observed)", context="Portal")
	_("National Day", context="Portal")
	_("Draft", context="Portal")
