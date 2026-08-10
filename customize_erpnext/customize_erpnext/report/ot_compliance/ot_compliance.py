# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Báo cáo tuân thủ trần làm thêm giờ.

Trần theo BLLĐ 2019 Điều 107 + NĐ 145/2020 Điều 61 — TIQN thuộc nhóm sản xuất/gia công
may mặc nên được áp mức đặc thù 300 giờ/năm. Ba mức trần lấy từ `TIQN Payroll Settings`.

Vì sao là báo cáo riêng chứ không phải cảnh báo lúc tính lương: khảo sát 2026 cho thấy
vượt trần trên diện rộng (393 NV vượt 40h chỉ riêng kỳ 07/2026). Nhét cảnh báo vào
Salary Slip sẽ sinh hàng trăm thông báo mỗi kỳ và không ai đọc.

Nguồn: `Attendance.custom_final_overtime_duration` (giờ chốt để trả lương), `docstatus = 1`.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Max, Sum
from frappe.utils import flt, getdate

from customize_erpnext.customize_erpnext.doctype.tiqn_payroll_settings.tiqn_payroll_settings import (
	get_settings,
)

OT_FIELD = "custom_final_overtime_duration"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not (filters.from_date and filters.to_date):
		frappe.throw(_("Vui lòng chọn khoảng thời gian."))

	settings = get_settings()
	caps = frappe._dict(
		day=flt(settings.ot_cap_per_day),
		month=flt(settings.ot_cap_per_month),
		year=flt(settings.ot_cap_per_year),
	)
	data = get_data(filters, caps)
	if filters.only_violations:
		data = [r for r in data if r["violations"]]
	return get_columns(caps), data


def get_columns(caps):
	return [
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link",
		 "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 190},
		{"fieldname": "department", "label": _("Department"), "fieldtype": "Link",
		 "options": "Department", "width": 150},
		{"fieldname": "max_day_hours", "label": _("Max / Day"), "fieldtype": "Float",
		 "width": 90, "precision": 1},
		{"fieldname": "period_hours", "label": _("In Period"), "fieldtype": "Float",
		 "width": 100, "precision": 1},
		{"fieldname": "ytd_hours", "label": _("Year to Date"), "fieldtype": "Float",
		 "width": 110, "precision": 1},
		{"fieldname": "remaining_year", "label": _("Remaining / Year"), "fieldtype": "Float",
		 "width": 130, "precision": 1},
		{"fieldname": "violations", "label": _("Exceeds"), "fieldtype": "Data", "width": 230},
	]


def get_data(filters, caps):
	period = _aggregate(filters.from_date, filters.to_date, filters)
	# Luỹ kế năm tính tới HẾT kỳ đang xem, không phải tới hôm nay — để rà lại kỳ cũ vẫn đúng.
	year_start = getdate(filters.to_date).replace(month=1, day=1)
	ytd = _aggregate(year_start, filters.to_date, filters)

	employees = _employee_info(set(period) | set(ytd))
	rows = []
	for emp, info in employees.items():
		p = period.get(emp, frappe._dict(total=0, max_day=0))
		y = ytd.get(emp, frappe._dict(total=0))
		violations = []
		if caps.day and flt(p.max_day) > caps.day:
			violations.append(_("day ({0}h > {1}h)").format(flt(p.max_day, 1), caps.day))
		if caps.month and flt(p.total) > caps.month:
			violations.append(_("period ({0}h > {1}h)").format(flt(p.total, 1), caps.month))
		if caps.year and flt(y.total) > caps.year:
			violations.append(_("year ({0}h > {1}h)").format(flt(y.total, 1), caps.year))

		rows.append({
			"employee": emp,
			"employee_name": info.employee_name,
			"department": info.department,
			"max_day_hours": flt(p.max_day, 1),
			"period_hours": flt(p.total, 1),
			"ytd_hours": flt(y.total, 1),
			"remaining_year": flt(caps.year - flt(y.total), 1) if caps.year else 0,
			"violations": " · ".join(violations),
		})

	# Người sắp chạm trần năm lên trước — đó là nhóm cần can thiệp, không phải nhóm đã vượt.
	rows.sort(key=lambda r: (-r["ytd_hours"], r["employee"]))
	return rows


def _aggregate(from_date, to_date, filters) -> dict:
	attendance = frappe.qb.DocType("Attendance")
	query = (
		frappe.qb.from_(attendance)
		.select(
			attendance.employee,
			Sum(attendance[OT_FIELD]).as_("total"),
			Max(attendance[OT_FIELD]).as_("max_day"),
		)
		.where(attendance.docstatus == 1)
		.where(attendance.attendance_date >= getdate(from_date))
		.where(attendance.attendance_date <= getdate(to_date))
		.where(attendance[OT_FIELD] > 0)
		.groupby(attendance.employee)
	)
	if filters.get("employee"):
		query = query.where(attendance.employee == filters.employee)
	if filters.get("department"):
		query = query.where(attendance.department == filters.department)
	if filters.get("company"):
		query = query.where(attendance.company == filters.company)

	return {r.employee: r for r in query.run(as_dict=True)}


def _employee_info(employees: set) -> dict:
	if not employees:
		return {}
	rows = frappe.get_all(
		"Employee",
		filters={"name": ("in", list(employees))},
		fields=["name", "employee_name", "department"],
		order_by="name asc",
	)
	return {r.name: r for r in rows}
