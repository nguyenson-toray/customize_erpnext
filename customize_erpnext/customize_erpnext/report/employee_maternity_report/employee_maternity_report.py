# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, date_diff, nowdate


def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data


def get_columns(filters=None):
	"""Define report columns"""
	show_detail = filters and filters.get("detail")

	columns = [
		{
			"fieldname": "maternity_record",
			"label": _("Maternity Record"),
			"fieldtype": "Link",
			"options": "Employee Maternity",
			"width": 160,
		},
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 120,
		},
		{
			"fieldname": "employee_name",
			"label": _("Employee Name"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "department",
			"label": _("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": 120,
		},
		{
			"fieldname": "custom_section",
			"label": _("Section"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "custom_group",
			"label": _("Group"),
			"fieldtype": "Data",
			"width": 100,
		},
		{
			"fieldname": "date_of_joining",
			"label": _("Date of Joining"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "seniority",
			"label": _("Seniority (Months)"),
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"fieldname": "type",
			"label": _("Maternity Type"),
			"fieldtype": "Data",
			"width": 130,
		},
		{
			"fieldname": "from_date",
			"label": _("From Date"),
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"fieldname": "to_date",
			"label": _("To Date"),
			"fieldtype": "Date",
			"width": 100,
		},
	]

	if show_detail:
		columns.append({
			"fieldname": "duration_days",
			"label": _("Duration (Days)"),
			"fieldtype": "Int",
			"width": 120,
		})

	columns.extend([
		{
			"fieldname": "estimated_due_date",
			"label": _("Estimated Due Date"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "date_of_birth",
			"label": _("Date of Birth"),
			"fieldtype": "Date",
			"width": 120,
		},
		{
			"fieldname": "gestational_age",
			"label": _("Gestational Age (Months)"),
			"fieldtype": "Float",
			"precision": 1,
			"width": 140,
		},
		{
			"fieldname": "note",
			"label": _("Note"),
			"fieldtype": "Data",
			"width": 200,
		},
	])

	if show_detail:
		columns.append({
			"fieldname": "relieving_date",
			"label": _("Relieving Date"),
			"fieldtype": "Date",
			"width": 120,
		})

	columns.append({
		"fieldname": "status",
		"label": _("Status"),
		"fieldtype": "Data",
		"width": 100,
	})

	return columns


def get_data(filters):
	"""
	Query Employee Maternity (cấu trúc mới: 1 record/employee) và expand
	thành nhiều rows — mỗi row là 1 giai đoạn (Pregnant / Maternity Leave / Young Child).

	Mọi giá trị phụ thuộc thời gian (status, seniority, gestational age) được tính
	theo filter `as_on_date` (mặc định hôm nay). Đây chỉ là tính lại khi chạy report —
	field `status` trên record KHÔNG bị thay đổi.
	"""
	conditions, params = _build_conditions(filters)

	records = frappe.db.sql(f"""
		SELECT
			mt.name          AS maternity_record,
			emp.name         AS employee,
			emp.employee_name,
			emp.department,
			emp.custom_section,
			emp.custom_group,
			emp.date_of_joining,
			emp.relieving_date,
			mt.pregnant_from_date,
			mt.pregnant_to_date,
			mt.estimated_due_date,
			mt.maternity_from_date,
			mt.maternity_from_date_estimate,
			mt.maternity_to_date,
			mt.youg_child_from_date,
			mt.youg_child_to_date,
			mt.date_of_birth,
			mt.apply_benefit,
			mt.note
		FROM `tabEmployee` emp
		INNER JOIN `tabEmployee Maternity` mt ON emp.name = mt.employee
		WHERE {conditions}
		ORDER BY emp.department, emp.custom_section, emp.custom_group, emp.employee_name
	""", params, as_dict=True)

	as_on_date = _get_as_on_date(filters)
	snapshot_only = filters.get("snapshot_only") if filters else None
	rows_by_employee = {}  # giữ thứ tự sắp xếp của câu SQL
	maternity_type_filter = filters.get("maternity_type") if filters else None

	for rec in records:
		seniority = _calc_seniority(rec.date_of_joining, as_on_date)

		# Giai đoạn Maternity: dùng ngày ước tính khi chưa có ngày nghỉ thật
		# (mirror Employee Maternity.calculate_status)
		effective_mat_from = rec.maternity_from_date or rec.maternity_from_date_estimate

		# Expand thành các rows theo từng giai đoạn
		periods = [
			{
				"type": "Pregnant",
				"from_date": rec.pregnant_from_date,
				"to_date": rec.pregnant_to_date,
			},
			{
				"type": "Maternity Leave",
				"from_date": effective_mat_from,
				"to_date": rec.maternity_to_date,
			},
			{
				"type": "Young Child",
				"from_date": rec.youg_child_from_date,
				"to_date": rec.youg_child_to_date,
			},
		]

		emp_rows = rows_by_employee.setdefault(rec.employee, [])
		for period in periods:
			if not period["from_date"]:
				continue  # Giai đoạn chưa có dữ liệu

			# Filter theo maternity_type nếu có
			if maternity_type_filter and period["type"] != maternity_type_filter:
				continue

			from_date = period["from_date"]
			to_date = period["to_date"]

			# Status tại as_on_date
			status = _calc_status(from_date, to_date, as_on_date)
			if filters and filters.get("status") and status != filters["status"]:
				continue

			# Duration
			eff_to = to_date or rec.estimated_due_date
			duration_days = (date_diff(eff_to, from_date) + 1) if eff_to else None

			# Gestational age (chỉ cho Pregnant)
			gestational_age = None
			if period["type"] == "Pregnant" and rec.estimated_due_date:
				gestational_age = _calc_gestational_age(rec.estimated_due_date, as_on_date)

			emp_rows.append({
				"maternity_record": rec.maternity_record,
				"employee": rec.employee,
				"employee_name": rec.employee_name,
				"department": rec.department,
				"custom_section": rec.custom_section,
				"custom_group": rec.custom_group,
				"date_of_joining": rec.date_of_joining,
				"seniority": seniority,
				"type": period["type"],
				"from_date": from_date,
				"to_date": to_date,
				"duration_days": duration_days,
				"estimated_due_date": rec.estimated_due_date if period["type"] == "Pregnant" else None,
				"date_of_birth": rec.date_of_birth if period["type"] == "Young Child" else None,
				"gestational_age": gestational_age,
				"note": rec.note,
				"relieving_date": rec.relieving_date,
				"status": status,
			})

	data = []
	for emp_rows in rows_by_employee.values():
		data.extend(_apply_snapshot(emp_rows, snapshot_only))

	return data


def _get_as_on_date(filters):
	"""Ngày mốc để tính trạng thái. Mặc định hôm nay."""
	value = filters.get("as_on_date") if filters else None
	return getdate(value or nowdate())


def _apply_snapshot(emp_rows, snapshot_only):
	"""Khi bật Snapshot: mỗi nhân viên chỉ còn 1 dòng — giai đoạn đang diễn ra
	tại as_on_date.

	Nếu 1 nhân viên có nhiều giai đoạn cùng Active (record trùng, hoặc dữ liệu cũ
	bị overlap) thì lấy giai đoạn có from_date mới nhất — cùng quy tắc ưu tiên với
	Employee Maternity.calculate_status().
	"""
	if not snapshot_only:
		return emp_rows

	active = [r for r in emp_rows if r["status"] == "Active"]
	if len(active) <= 1:
		return active

	active.sort(key=lambda r: getdate(r["from_date"]), reverse=True)
	return active[:1]


def _build_conditions(filters):
	"""Build WHERE clause và params dict"""
	if not filters:
		filters = {}

	conditions = ["1=1"]
	params = {}

	if filters.get("employee"):
		conditions.append("emp.name = %(employee)s")
		params["employee"] = filters["employee"]

	if filters.get("employee_name"):
		conditions.append("emp.employee_name LIKE %(employee_name_like)s")
		params["employee_name_like"] = f"%{filters['employee_name']}%"

	if filters.get("department"):
		conditions.append("emp.department = %(department)s")
		params["department"] = filters["department"]

	if filters.get("custom_section"):
		conditions.append("emp.custom_section = %(custom_section)s")
		params["custom_section"] = filters["custom_section"]

	if filters.get("custom_group"):
		conditions.append("emp.custom_group = %(custom_group)s")
		params["custom_group"] = filters["custom_group"]

	return " AND ".join(conditions), params


def _calc_seniority(date_of_joining, as_on_date):
	if not date_of_joining:
		return 0
	from dateutil.relativedelta import relativedelta
	doj = getdate(date_of_joining)
	if doj >= as_on_date:
		return 0  # as_on_date trước ngày vào làm
	rd = relativedelta(as_on_date, doj)
	return rd.years * 12 + rd.months


def _calc_gestational_age(estimated_due_date, as_on_date):
	"""Gestational age in months: 9.5 - (complete months to due date + 1)"""
	from dateutil.relativedelta import relativedelta
	edd = getdate(estimated_due_date)
	if edd <= as_on_date:
		return 9.5
	rd = relativedelta(edd, as_on_date)
	months_diff = rd.years * 12 + rd.months
	return round(9.5 - (months_diff + 1), 1)


def _calc_status(from_date, to_date, as_on_date):
	if not from_date:
		return None
	from_d = getdate(from_date)
	if as_on_date < from_d:
		return "Upcoming"
	if to_date is None or from_d <= as_on_date <= getdate(to_date):
		return "Active"
	return "Completed"
