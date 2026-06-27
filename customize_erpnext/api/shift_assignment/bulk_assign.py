"""
Bulk creation of Shift Assignment records.

Used by the "Bulk Create" action on the Shift Assignment list view.
Targets can be selected either by an explicit list of employees or by
custom_group (Employee.custom_group -> "Group"). One submitted Shift
Assignment is created per matched employee.
"""

import json

import frappe
from frappe import _
from frappe.utils import getdate


def _resolve_employees(employees=None, custom_group=None, start_date=None, end_date=None):
	"""Resolve the target employee list from explicit list or custom_group filter.

	Only Active employees (or Left employees still active in the period) are
	returned. The period used for the "active" check is [start_date, end_date],
	defaulting end_date to start_date when open-ended.
	"""
	if employees:
		# Explicit selection — keep as given (already valid employee names)
		return list(dict.fromkeys(employees))  # de-dupe, preserve order

	from_date = getdate(start_date)
	to_date = getdate(end_date) if end_date else from_date

	conditions = ["""
		(
			(emp.status = 'Active'
			 AND (emp.date_of_joining IS NULL OR emp.date_of_joining <= %(to_date)s))
			OR
			(emp.status = 'Left'
			 AND (emp.date_of_joining IS NULL OR emp.date_of_joining <= %(to_date)s)
			 AND (emp.relieving_date IS NULL OR emp.relieving_date > %(from_date)s))
		)
	"""]
	values = {"from_date": from_date, "to_date": to_date}

	if custom_group:
		conditions.append("emp.custom_group = %(custom_group)s")
		values["custom_group"] = custom_group

	rows = frappe.db.sql(
		f"""
		SELECT emp.name
		FROM `tabEmployee` emp
		WHERE {" AND ".join(conditions)}
		ORDER BY emp.name
		""",
		values,
	)
	return [r[0] for r in rows] if rows else []


def _has_overlapping_assignment(employee, start_date, end_date):
	"""Return True if the employee already has an Active assignment overlapping
	[start_date, end_date]. Open-ended assignments (no end_date) are treated as
	extending to infinity."""
	end_clause = end_date or "9999-12-31"
	existing = frappe.db.sql(
		"""
		SELECT name
		FROM `tabShift Assignment`
		WHERE employee = %(employee)s
		  AND docstatus = 1
		  AND status = 'Active'
		  AND start_date <= %(end_date)s
		  AND COALESCE(end_date, '9999-12-31') >= %(start_date)s
		LIMIT 1
		""",
		{"employee": employee, "start_date": start_date, "end_date": end_clause},
	)
	return bool(existing)


@frappe.whitelist()
def bulk_create_shift_assignment(
	shift_type,
	start_date,
	company,
	end_date=None,
	employees=None,
	custom_group=None,
	status="Active",
	skip_existing=1,
):
	"""Create (and submit) a Shift Assignment for each matched employee.

	Args:
		shift_type: Shift Type to assign (required).
		start_date: Assignment start date (required).
		company: Company (required by Shift Assignment).
		end_date: Optional assignment end date (open-ended if empty).
		employees: Optional JSON list (or list) of employee names.
		custom_group: Optional Employee.custom_group filter (ignored if employees given).
		status: Assignment status, default "Active".
		skip_existing: If truthy, skip employees with an overlapping Active assignment.

	Returns:
		dict: { created, skipped, errors[], created_names[] }
	"""
	if not frappe.has_permission("Shift Assignment", "create"):
		frappe.throw(_("Not permitted to create Shift Assignment"), frappe.PermissionError)

	if not shift_type:
		frappe.throw(_("Shift Type is required"))
	if not start_date:
		frappe.throw(_("Start Date is required"))
	if not company:
		frappe.throw(_("Company is required"))

	if isinstance(employees, str):
		employees = json.loads(employees) if employees.strip() else None

	skip_existing = int(skip_existing or 0)

	if end_date and getdate(end_date) < getdate(start_date):
		frappe.throw(_("End Date cannot be before Start Date"))

	target_employees = _resolve_employees(
		employees=employees,
		custom_group=custom_group,
		start_date=start_date,
		end_date=end_date,
	)

	if not target_employees:
		frappe.throw(_("No employees matched the selected filter"))

	result = {"created": 0, "skipped": 0, "errors": [], "created_names": []}

	for employee in target_employees:
		try:
			if skip_existing and _has_overlapping_assignment(employee, start_date, end_date):
				result["skipped"] += 1
				continue

			doc = frappe.get_doc({
				"doctype": "Shift Assignment",
				"employee": employee,
				"shift_type": shift_type,
				"company": company,
				"start_date": start_date,
				"end_date": end_date or None,
				"status": status,
			})
			doc.insert()
			doc.submit()
			# Commit per record so a later failure's rollback cannot undo
			# already-created assignments.
			frappe.db.commit()
			result["created"] += 1
			result["created_names"].append(doc.name)
		except Exception as e:
			# Roll back only this employee's partial work, keep going with the rest
			frappe.db.rollback()
			result["skipped"] += 1
			result["errors"].append({"employee": employee, "error": str(e)})

	return result
