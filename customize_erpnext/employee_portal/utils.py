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


# Phone columns on Employee, in priority order (23/10/2026): the HR phone first; the
# Zalo phone (custom_cell_phone_zalo, created by HR) only when no cell_number matches.
# A column that does not exist (yet) is skipped.
PHONE_FIELDS = ("cell_number", "custom_cell_phone_zalo")


def is_review_phone(phone):
	"""True when `phone` is listed in Settings > Zalo App Review and Review Mode is on.
	Such a user sees the SAMPLE data of employee_portal/demo.py, never a real record."""
	s = get_settings()
	key = phone_key(phone)
	if not key or not cint(s.get("review_mode")):
		return False
	return key in {phone_key(p) for p in re.split(r"[\s,;]+", s.get("review_phones") or "")}


def find_employees_by_phone(phone):
	"""Employees whose phone matches `phone`, newest first.

	cell_number is checked first; custom_cell_phone_zalo only when no employee has the
	number as cell_number (so an employee whose Zalo phone differs from the HR one can
	still sign in, without stealing a number that is someone's cell_number).
	Newest = latest date_of_joining, then highest employee code: someone who left and
	came back gets a NEW code but keeps the old number, and the new code must win.
	"""
	key = phone_key(phone)
	if not key:
		return []
	meta = frappe.get_meta("Employee")
	for field in PHONE_FIELDS:
		if field != "cell_number" and not meta.has_field(field):
			continue
		rows = frappe.db.sql(
			f"""
			SELECT name, employee_name, status, relieving_date, date_of_joining, `{field}` AS matched_phone,
			       %s AS matched_field
			FROM `tabEmployee`
			WHERE IFNULL(`{field}`, '') != ''
			  AND RIGHT(REGEXP_REPLACE(`{field}`, '[^0-9]', ''), 9) = %s
			ORDER BY date_of_joining DESC, name DESC
			""",
			(field, key),
			as_dict=True,
		)
		if rows:
			return rows
	return []


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



# ---------------------------------------------------------------------------
# Payslip lines (v4, 26/10/2026): TIQN Payslip alone describes the payslip - no
# HRMS Salary Component involved. One field per paper line, named after its code
# ("3.2" -> `sc_3_2`), labelled "<code> <short English> (formula letters)" (v5) - the
# Excel / Data Import column header:
#     "3.2 Technical Allowance", "3 Monthly Salary (c=a+b)"
# code -> order and parent, "(a)" / "(c=a+b)" -> formula letters
# (api/employee_portal/payslip.py). The Mini App text is CnB's, word for word with the
# line number and letters ("9 Thực lĩnh (j=f-g+h+i)"): Employee Portal Settings >
# Payslip Lines; empty -> the field label.
#
# A paper line may carry TWO values: the amount and a number in the "Unit/ĐVT"
# column (1.2 = 27 days + 17.214.001 VND). The second one is `sc_<code>_qty`, a Float
# labelled "<code> Days" / "<code> Hours". A Float `sc_<code>` without its amount
# (1.1) is a days-only line.
#
# Adding a line = IT adds the field(s) to TIQN Payslip + migrate; the Settings row
# appears by itself (CnB then types the Mini App label).
# ---------------------------------------------------------------------------
PAYSLIP_DT = "TIQN Payslip"
COMPONENT_FIELD_PREFIX = "sc_"
QTY_FIELD_SUFFIX = "_qty"
COMPONENT_FIELD_RE = re.compile(r"^sc_(\d+(?:_\d+)*)$")
QTY_UNIT_RE = re.compile(r"(?:^|[\s-])(days?|hours?)\s*$", re.IGNORECASE)

# What the field labels cannot say. Paper payslip, fixed:
# - 3.2-3.10 are the details of 3.1 "Allowance (d)", not of 3 "Monthly Salary (c=a+b)",
#   and 3.1 itself is a main line (level 0);
GROUP_PARENT = {"3": "3.1"}
# - totals of a block (Section Total) and of a group that is shown even when 0 (Subtotal);
SECTION_TOTALS = ("5", "6", "7", "8", "9")
SUBTOTALS = ("3", "3.1", "4")
# - block of each top-level code. The detail lines of 1 and 2 (days, overtime) went to
#   ATTENDANCE in the deprecated `sections` payload.
SECTION_OF = {
	"1": "Earnings", "2": "Earnings", "3": "Earnings", "4": "Earnings", "5": "Earnings",
	"6": "Deductions", "7": "Others", "8": "Adjustment", "9": "Net Pay",
}
ATTENDANCE_GROUPS = ("1", "2")


def component_fieldname(abbr):
	return COMPONENT_FIELD_PREFIX + str(abbr or "").strip().replace(".", "_")


def component_qty_fieldname(abbr):
	return component_fieldname(abbr) + QTY_FIELD_SUFFIX


def code_key(abbr):
	"""Sort key of a code: 1, 1.1, 1.2, 2, ... 3.9, 3.10, 4."""
	return [int(p) for p in str(abbr).split(".") if p.isdigit()]


def portal_label(label):
	"""Default Mini App label of a payslip field label: the part after the first "/"
	(older bilingual labels), without the code and formula letters:
	"1 Basic Salary/Lương cơ bản  (a)"          -> "Lương cơ bản"
	"9 Net Salary/Thực lĩnh (j=f-g+h+i):"       -> "Thực lĩnh"
	"7.6 21.5% (SI+HI+UI)/21.5% (BHXH+BHYT+BHTN)" -> "21.5% (BHXH+BHYT+BHTN)"
	The formula letters are sent apart (`formula`) - the Mini App shows "label (formula)".
	"""
	text = re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", label or "")
	if "/" in text:
		text = text.split("/", 1)[1]
	text = re.sub(r"\(\s*[a-j](?:\s*=[^)]*)?\s*\)\s*:?\s*$", "", text.strip())
	return " ".join(text.strip(" :").split())


def strip_code_formula(text):
	"""Line text without its leading number and trailing formula letters:
	"9 Thực lĩnh (j=f-g+h+i)" -> "Thực lĩnh" (the `label` older Mini App builds put
	between `no` and `formula`)."""
	text = re.sub(r"^\s*\d+(?:\.\d+)*\s*", "", text or "")
	# Only real letters - the same shape payslip.FORMULA_RE sends as `formula`; any other
	# note in brackets stays in the text.
	text = re.sub(r"\(\s*[a-j](?:\s*=\s*[a-j](?:\s*[+-]\s*[a-j])*)?\s*\)\s*:?\s*$", "", text.strip())
	return " ".join(text.strip(" :").split())


def _qty_unit(label):
	m = QTY_UNIT_RE.search(label or "")
	return "Hour" if m and m.group(1).lower().startswith("hour") else "Day"


def _parent_code(abbr, codes):
	parts = str(abbr).split(".")
	if len(parts) < 2 or abbr in GROUP_PARENT.values():  # 3.1 is a main line of its own
		return None
	parent = ".".join(parts[:-1])
	grouped = GROUP_PARENT.get(parent)
	if grouped and grouped != abbr and grouped in codes:
		return grouped
	return parent if parent in codes else None


def payslip_component_fields():
	"""Every line of the payslip, in code order, read from the TIQN Payslip fields:

	name          field label as on the paper ("1.2 Actual working days/Số ngày công...")
	abbr          code "1.2"
	fieldname     `sc_1_2` - the amount (or the days of a days-only line)
	qty_fieldname `sc_1_2_qty` or None; qty_unit "Day" | "Hour" | None; qty_label
	unit          "VND", or "Day" / "Hour" for a days-only line (1.1)
	display_label Mini App text as shown, number + letters included: Settings > Payslip
	              Lines, else `name`
	label         display_label without number / letters (older Mini App builds)
	parent        `name` of the group line, or None
	section, row_type ("Line" | "Subtotal" | "Section Total") - see the tables above
	"""
	meta = frappe.get_meta(PAYSLIP_DT)
	app_labels = payslip_app_labels()
	lines = {}
	for df in meta.fields:
		m = COMPONENT_FIELD_RE.match(df.fieldname)
		if m and df.fieldtype in ("Currency", "Float", "Int"):
			lines[m.group(1).replace("_", ".")] = df

	out = []
	for abbr in sorted(lines, key=code_key):
		df = lines[abbr]
		qty = meta.get_field(component_qty_fieldname(abbr))
		top = abbr.split(".")[0]
		days_only = df.fieldtype != "Currency"
		out.append(
			frappe._dict(
				name=df.label or df.fieldname,
				abbr=abbr,
				fieldname=df.fieldname,
				qty_fieldname=qty.fieldname if qty and not days_only else None,
				qty_unit=_qty_unit(qty.label) if qty and not days_only else None,
				qty_label=qty.label if qty and not days_only else None,
				unit=_qty_unit(df.label) if days_only else "VND",
				display_label=app_labels.get(df.fieldname) or df.label or abbr,
				parent_code=_parent_code(abbr, lines),
				section=("Attendance" if top in ATTENDANCE_GROUPS and abbr != top else SECTION_OF.get(top)),
				row_type=(
					"Section Total" if abbr in SECTION_TOTALS else "Subtotal" if abbr in SUBTOTALS else "Line"
				),
			)
		)
	names = {c.abbr: c.name for c in out}
	for c in out:
		c.parent = names.get(c.parent_code)
		c.label = strip_code_formula(c.display_label) or c.display_label
	return out


def payslip_app_labels():
	"""{payslip field: Mini App label} typed by CnB in Settings > Payslip Lines."""
	return {
		r.payslip_field: (r.portal_label or "").strip()
		for r in get_settings().get("payslip_lines") or []
		if r.payslip_field and (r.portal_label or "").strip()
	}


def payslip_value_fieldnames(components=None):
	"""Every number field of a payslip: amounts and days / hours values."""
	out = []
	for c in components or payslip_component_fields():
		out.append(c.fieldname)
		if c.qty_fieldname:
			out.append(c.qty_fieldname)
	return out


def payslip_field_mismatches():
	"""`sc_*` fields the payslip cannot use - config errors IT must fix on TIQN Payslip:
	a days / hours field without its amount field, or a `sc_` field whose name is not a code."""
	meta = frappe.get_meta(PAYSLIP_DT)
	used = set(payslip_value_fieldnames())
	return [
		df.fieldname
		for df in meta.fields
		if df.fieldname.startswith(COMPONENT_FIELD_PREFIX) and df.fieldname not in used
	]


# ---------------------------------------------------------------------------
# Zalo "ID by OA" (getUserInfo().idByOA) - the only ID openChat({type: "user"}) accepts.
# The app-scoped zalo_user_id looks just as valid but opens nothing (lesson from the
# vehicle Mini App, vehicle_management/API_CONTRACT.md "zalo_user_id KHÔNG mở được chat").
# ---------------------------------------------------------------------------
MIN_ID_BY_OA_DIGITS = 10  # same shape check as TIQN Zalo Role Map


def clean_id_by_oa(value):
	"""Stripped ID, None when empty; raises ValidationError when it is not digits-only
	and at least MIN_ID_BY_OA_DIGITS long (a placeholder like "34" would show a chat
	button that silently does nothing)."""
	value = str(value or "").strip()
	if not value:
		return None
	if not value.isdigit() or len(value) < MIN_ID_BY_OA_DIGITS:
		frappe.throw(
			frappe._("{0} does not look like a Zalo ID by OA - digits only, at least {1} of them.").format(
				value, MIN_ID_BY_OA_DIGITS
			)
		)
	return value
