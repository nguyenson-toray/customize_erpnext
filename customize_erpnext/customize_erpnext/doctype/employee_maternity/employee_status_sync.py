# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Keep `Employee.status` in step with the maternity cycle, and expose the
sub-status that the read-only `Employee.custom_sub_status` HTML field renders.

Only `Maternity Leave` means the employee is actually away — `Pregnant` and
`Young Child` still work a normal roster (they only earn the one-hour early
leave benefit), so those phases keep the employee `Active`.

`custom_sub_status` is an HTML field: it has no database column and stores
nothing. `get_employee_sub_status()` derives it live from Employee Maternity
every time the form renders.
"""

import frappe
from frappe import _
from frappe.utils import getdate

MATERNITY_LEAVE = "Maternity Leave"

# Employee statuses this module is allowed to flip. `Left` and `Suspended` are
# lifecycle decisions HR made for other reasons — never overwrite them.
FLIPPABLE_STATUSES = ("Active", "Inactive")

# Which Employee Maternity record wins when an employee holds several (a second
# cycle, or a duplicate). Lower number = higher priority. Records with a blank
# status never win — they describe no phase at all.
PHASE_PRIORITY = {
	MATERNITY_LEAVE: 0,
	"Pregnant": 1,
	"Young Child": 2,
	"Inactive": 3,
}

PHASE_INDICATOR = {
	MATERNITY_LEAVE: "orange",
	"Pregnant": "blue",
	"Young Child": "green",
	"Inactive": "gray",
}


# =============================================================================
# Employee.status sync
# =============================================================================

def sync_employee_status(employee, old_status, new_status, record=None):
	"""Flip `Employee.status` when a maternity record enters or leaves `Maternity Leave`.

	Acts on **transitions only** (old != new). Steady state is deliberately left
	alone: the daily scheduler re-runs over every record, and reasserting a status
	on each pass would stomp whatever HR set by hand in between.
	"""
	if not employee:
		return

	old_status = old_status or ""
	new_status = new_status or ""
	if old_status == new_status:
		return

	if new_status == MATERNITY_LEAVE:
		_set_employee_status(employee, "Inactive", record, new_status)
	elif old_status == MATERNITY_LEAVE:
		# A second cycle may still be running on another record — an employee can
		# hold more than one Employee Maternity row, so leaving this one is not
		# proof the employee is back at work.
		if _has_other_maternity_leave(employee, record):
			return
		_set_employee_status(employee, "Active", record, new_status)


def _has_other_maternity_leave(employee, exclude_record):
	filters = {"employee": employee, "status": MATERNITY_LEAVE}
	if exclude_record:
		filters["name"] = ("!=", exclude_record)
	return bool(frappe.db.exists("Employee Maternity", filters))


def _set_employee_status(employee, target, record, phase):
	"""Write Employee.status, skipping anything outside the Active/Inactive pair.

	Uses db.set_value rather than doc.save(): the Employee lifecycle clears the
	whole site cache and disables the linked User on every save, and neither
	belongs in a maternity phase change.
	"""
	current = frappe.db.get_value("Employee", employee, "status")
	if current is None:
		return  # employee was deleted
	if current == target or current not in FLIPPABLE_STATUSES:
		return

	frappe.db.set_value("Employee", employee, "status", target)

	# Status flips on a batch of people with no visible cause are hard to audit
	# later, so leave a breadcrumb naming the record that caused it.
	reason = _("Maternity phase {0}").format(phase or _("cleared"))
	if record:
		reason = f"{reason} ({record})"
	try:
		frappe.get_doc({
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Employee",
			"reference_name": employee,
			"content": _("Status {0} → {1} — {2}").format(current, target, reason),
		}).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(), "Employee Maternity status sync: comment failed"
		)


# =============================================================================
# Sub-status (display only — nothing is stored)
# =============================================================================

def _phase_start(row):
	"""First day of the phase the record's status refers to."""
	if row.status == "Pregnant":
		return row.pregnant_from_date
	if row.status == MATERNITY_LEAVE:
		return row.maternity_from_date or row.maternity_from_date_estimate
	if row.status == "Young Child":
		return row.youg_child_from_date
	return row.youg_child_to_date  # Inactive = everything already finished


def get_current_maternity_record(employee):
	"""The maternity record that describes the employee right now, or None.

	Deterministic by design: an employee can hold two or three records and a bare
	`LIMIT 1` would pick an arbitrary one. Ranks by phase priority, then by the
	latest phase start, then by the most recently touched record.
	"""
	if not employee:
		return None

	rows = frappe.get_all(
		"Employee Maternity",
		filters={"employee": employee, "status": ("in", list(PHASE_PRIORITY))},
		fields=[
			"name", "status", "modified",
			"pregnant_from_date", "pregnant_to_date",
			"maternity_from_date", "maternity_from_date_estimate", "maternity_to_date",
			"youg_child_from_date", "youg_child_to_date",
		],
	)
	if not rows:
		return None

	def sort_key(row):
		start = _phase_start(row)
		return (
			PHASE_PRIORITY.get(row.status, 99),
			-(getdate(start).toordinal() if start else 0),
			-row.modified.timestamp(),
		)

	return sorted(rows, key=sort_key)[0]


def _phase_range(row):
	if row.status == "Pregnant":
		return row.pregnant_from_date, row.pregnant_to_date
	if row.status == MATERNITY_LEAVE:
		return (row.maternity_from_date or row.maternity_from_date_estimate), row.maternity_to_date
	if row.status == "Young Child":
		return row.youg_child_from_date, row.youg_child_to_date
	return None, row.youg_child_to_date


@frappe.whitelist()
def get_employee_sub_status(employee):
	"""Payload for the `custom_sub_status` HTML field. Returns None when there is
	nothing to show.

	Maternity is currently the only source of a sub-status, but the shape is kept
	generic (`label`/`source`/`reference`) so other reasons for Inactive or
	Suspended can be added without changing the client.
	"""
	row = get_current_maternity_record(employee)
	if not row:
		return None

	from_date, to_date = _phase_range(row)
	return {
		"label": row.status,
		"indicator": PHASE_INDICATOR.get(row.status, "gray"),
		"source": "Employee Maternity",
		"reference": row.name,
		"from_date": str(from_date) if from_date else None,
		"to_date": str(to_date) if to_date else None,
		"on_leave": row.status == MATERNITY_LEAVE,
	}


def is_inactive_for_maternity(employee):
	"""True when the employee is Inactive because they are on maternity leave.

	Used to hold the linked User account open — being on maternity leave is not a
	reason to lock somebody out of their payslips and leave applications.
	"""
	if not employee:
		return False
	return _has_other_maternity_leave(employee, exclude_record=None)
