# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Shared helpers for the Employee Portal (Zalo Mini App) module.

Kept free of request handling so the Desk side (payslip upload, reports) and the
Mini App API use exactly the same period / phone rules. Contract:
`employee_portal/API_CONTRACT.md`.
"""

import calendar
import datetime
import re

import frappe
from frappe.utils import add_days, cint, getdate

SETTINGS = "Employee Portal Settings"

# TIQN closes attendance on the 25th: period "2026-08" runs 26/07 -> 25/08.
PERIOD_END_DAY = 25
PERIOD_RE = re.compile(r"^(\d{4})-(\d{2})$")


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
def get_settings():
	return frappe.get_cached_doc(SETTINGS)


def setting_int(fieldname, default):
	value = get_settings().get(fieldname)
	return cint(value) if value not in (None, "") else default


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------
def validate_period(period):
	"""Return `period` if it is a well-formed "YYYY-MM", else throw."""
	period = (period or "").strip()
	m = PERIOD_RE.match(period)
	if not m or not 1 <= int(m.group(2)) <= 12:
		frappe.throw(frappe._("Period must look like YYYY-MM, got {0}").format(period or "''"))
	return period


def period_bounds(period):
	"""(from_date, to_date) of a pay period. "2026-08" -> (2026-07-26, 2026-08-25)."""
	year, month = (int(x) for x in validate_period(period).split("-"))
	to_date = datetime.date(year, month, PERIOD_END_DAY)
	prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
	from_date = datetime.date(prev_year, prev_month, PERIOD_END_DAY + 1)
	return from_date, to_date


def period_of_date(date):
	"""The pay period a calendar date belongs to. 26/07 and 25/08 are both "2026-08"."""
	date = getdate(date)
	year, month = date.year, date.month
	if date.day > PERIOD_END_DAY:
		year, month = (year + 1, 1) if month == 12 else (year, month + 1)
	return f"{year:04d}-{month:02d}"


def shift_period(period, months):
	year, month = (int(x) for x in validate_period(period).split("-"))
	index = year * 12 + (month - 1) + months
	return f"{index // 12:04d}-{index % 12 + 1:02d}"


def period_label(period):
	""""2026-08" -> "08/2026" (callers prefix "Tháng"/"Phiếu lương" themselves)."""
	year, month = validate_period(period).split("-")
	return f"{month}/{year}"


def expected_pay_date(period):
	"""Pay day (Settings, default 5) of the month AFTER the period ends."""
	day = setting_int("expected_pay_day", 5)
	if not day:
		return None
	year, month = (int(x) for x in shift_period(period, 1).split("-"))
	return datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def parse_period_cell(value):
	"""Read the "Kỳ lương" cell of the HR Excel file into "YYYY-MM".

	Accepts "10-2026", "10/2026", "2026-10", "2026/10" and real dates - Excel quietly
	turns "10-2026" into 01/10/2026 when the column is not formatted as text.
	Returns None when the cell cannot be read.
	"""
	if value in (None, ""):
		return None
	if isinstance(value, (datetime.datetime, datetime.date)):
		return f"{value.year:04d}-{value.month:02d}"
	text = str(value).strip()
	m = re.match(r"^(\d{1,2})\s*[-/.]\s*(\d{4})$", text)
	if m:
		year, month = int(m.group(2)), int(m.group(1))
	else:
		m = re.match(r"^(\d{4})\s*[-/.]\s*(\d{1,2})$", text)
		if not m:
			return None
		year, month = int(m.group(1)), int(m.group(2))
	if not 1 <= month <= 12:
		return None
	return f"{year:04d}-{month:02d}"


# ---------------------------------------------------------------------------
# Phones
# ---------------------------------------------------------------------------
def phone_key(phone):
	"""Last 9 digits - the part every way of writing a VN mobile number agrees on.

	0905123456, 84905123456, +84 905 123 456 and 905123456 (Excel ate the leading 0,
	true for ~1.140 Employee rows) all give "905123456". Returns None if there are
	fewer than 9 digits.
	"""
	digits = re.sub(r"\D", "", str(phone or ""))
	return digits[-9:] if len(digits) >= 9 else None


def local_phone(phone):
	key = phone_key(phone)
	return f"0{key}" if key else None


def mask_phone(phone):
	"""0962200054 -> "09•• ••• 054". Never send a full number back to the client."""
	local = local_phone(phone)
	if not local:
		return None
	return f"{local[:2]}•• ••• {local[-3:]}"


def find_employees_by_phone(phone):
	"""Employees whose cell_number matches `phone`, newest first.

	Newest = latest date_of_joining, then highest employee code: someone who left and
	came back gets a NEW code but keeps the old number, and the new code must win.
	"""
	key = phone_key(phone)
	if not key:
		return []
	return frappe.db.sql(
		"""
		SELECT name, employee_name, status, relieving_date, date_of_joining, cell_number
		FROM `tabEmployee`
		WHERE IFNULL(cell_number, '') != ''
		  AND RIGHT(REGEXP_REPLACE(cell_number, '[^0-9]', ''), 9) = %s
		ORDER BY date_of_joining DESC, name DESC
		""",
		key,
		as_dict=True,
	)


# ---------------------------------------------------------------------------
# Employee access
# ---------------------------------------------------------------------------
def employee_access(employee_row, today=None):
	"""Decide what an employee may do in the portal.

	Returns (result, read_only_until, expired_on) where result is one of
	ACTIVE / READ_ONLY / EXPIRED.

	🔴 `relieving_date` is the FIRST day off, not the last day worked, so the
	read-only window is counted from it as-is.
	⚠ Employee.status holds "Left " with a trailing space on some rows - strip it.
	"""
	today = getdate(today)
	status = (employee_row.get("status") or "").strip()
	if status == "Active":
		return "ACTIVE", None, None
	if status == "Left" and employee_row.get("relieving_date"):
		until = add_days(getdate(employee_row["relieving_date"]), setting_int("read_only_days", 30))
		until = getdate(until)
		if today < until:
			return "READ_ONLY", until, None
		return "EXPIRED", None, until
	return "EXPIRED", None, None


def initials(full_name):
	""""Nguyễn Văn An" -> "NA" (first letter of the family name and the given name)."""
	parts = [p for p in (full_name or "").split() if p]
	if not parts:
		return ""
	if len(parts) == 1:
		return parts[0][:1].upper()
	return (parts[0][:1] + parts[-1][:1]).upper()


def strip_company_suffix(value):
	""""Production - TIQN" -> "Production"."""
	return re.sub(r"\s+-\s+TIQN$", "", value or "") or None


def designation_label(designation):
	"""Vietnamese job title shown in the Mini App.

	Read from Designation.custom_designation_vn, NOT from Employee.custom_designation_vietnamese:
	that one is a fetch_from copy that never refreshes once filled, so a renamed title would
	stay stale on every employee. Falls back to the Designation name.
	"""
	if not designation:
		return None
	vn = frappe.get_cached_value("Designation", designation, "custom_designation_vn")
	return (vn or "").strip() or designation

