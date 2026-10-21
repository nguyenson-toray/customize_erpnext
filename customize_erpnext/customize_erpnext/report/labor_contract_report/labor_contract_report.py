# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	get_first_day,
	get_first_day_of_week,
	get_last_day,
	get_last_day_of_week,
	getdate,
	nowdate,
)

from customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract import business_today

# Who may download personal data (ID card, address, bank, salary) for drafting
# contracts. The report itself is also open to Department/Factory Managers.
EXPORT_ROLES = ("HR Manager", "HR User", "System Manager")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "name", "label": _("ID"), "fieldtype": "Link",
		 "options": "Labor Contract", "width": 170},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link",
		 "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data",
		 "width": 190},
		{"fieldname": "designation", "label": _("Designation"), "fieldtype": "Link",
		 "options": "Designation", "width": 150},
		{"fieldname": "custom_section", "label": _("Section"), "fieldtype": "Link",
		 "options": "Section", "width": 120},
		{"fieldname": "custom_group", "label": _("Group"), "fieldtype": "Link",
		 "options": "Group", "width": 120},
		{"fieldname": "contract_type", "label": _("Contract Type"), "fieldtype": "Link",
		 "options": "Employment Type", "width": 220},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "start_date", "label": _("Start Date"), "fieldtype": "Date",
		 "width": 105},
		{"fieldname": "end_date", "label": _("End Date"), "fieldtype": "Date",
		 "width": 105},
		{"fieldname": "days_left", "label": _("Days Left"), "fieldtype": "Int",
		 "width": 90},
		{"fieldname": "next_contract_type", "label": _("Next Contract Type"),
		 "fieldtype": "Link", "options": "Employment Type", "width": 200},
		{"fieldname": "next_sign_date", "label": _("Next Sign Date"), "fieldtype": "Date",
		 "width": 115},
		{"fieldname": "relieving_date", "label": _("Relieving Date"), "fieldtype": "Date",
		 "width": 115},
	]


def _expiring_range(filters, today):
	"""(from, to) for the "Expiring" preset, matched against end_date."""
	preset = filters.get("expiring")
	# Calendar weeks; the first day follows System Settings (Monday on this site)
	if preset == "This Week":
		return get_first_day_of_week(today), get_last_day_of_week(today)
	if preset == "Next Week":
		next_week = add_days(today, 7)
		return get_first_day_of_week(next_week), get_last_day_of_week(next_week)
	if preset == "This Month":
		return get_first_day(today), get_last_day(today)
	if preset == "Next Month":
		next_month = add_months(today, 1)
		return get_first_day(next_month), get_last_day(next_month)
	if preset == "Next 30 Days":
		return today, add_days(today, 30)
	if preset == "Next 60 Days":
		return today, add_days(today, 60)
	if preset == "Custom":
		return filters.get("from_date"), filters.get("to_date")
	return None, None


def _build_conditions(filters):
	today = getdate(business_today())
	conditions = []
	values = {"today": today}

	for field in ("employee", "status", "contract_type", "custom_section", "custom_group"):
		if filters.get(field):
			conditions.append(f"lc.{field} = %({field})s")
			values[field] = filters[field]

	# The contract in force today — one row per employee, since a chain never
	# overlaps. Someone who already left (relieving_date = first day off) has no
	# contract in force even if its end date is later. An unchecked Check filter
	# is not sent at all, so test truthiness.
	if filters.get("current_only"):
		conditions.append(
			"lc.start_date <= %(today)s AND (lc.end_date IS NULL OR lc.end_date >= %(today)s)"
			" AND (emp.relieving_date IS NULL OR emp.relieving_date > %(today)s)"
		)

	from_date, to_date = _expiring_range(filters, today)
	if from_date:
		conditions.append("lc.end_date >= %(expiring_from)s")
		values["expiring_from"] = from_date
	if to_date:
		conditions.append("lc.end_date <= %(expiring_to)s")
		values["expiring_to"] = to_date

	where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
	return where, values


def get_data(filters):
	where, values = _build_conditions(filters)

	return frappe.db.sql(
		f"""
		SELECT
			lc.name, lc.employee, lc.employee_name, lc.designation,
			lc.custom_section, lc.custom_group, lc.contract_type, lc.status,
			lc.start_date, lc.end_date,
			-- Only for a contract still waiting on its renewal: blank once the next
			-- stage exists or the employee has left (relieving_date = first day off),
			-- otherwise every past stage of the chain shows a large negative number
			IF(lc.next_stage_created = 1
					OR (emp.relieving_date IS NOT NULL AND emp.relieving_date <= %(today)s),
				NULL, DATEDIFF(lc.end_date, %(today)s)) AS days_left,
			et.custom_warning_before AS warning_before,
			lc.next_contract_type, lc.next_sign_date, emp.relieving_date,
			-- relieving_date = first day off: leaving on/before the next sign date
			-- means there is no next contract to sign
			(emp.relieving_date IS NOT NULL AND lc.next_sign_date IS NOT NULL
				AND emp.relieving_date <= lc.next_sign_date) AS leaves_before_next
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		LEFT JOIN `tabEmployment Type` et ON et.name = lc.contract_type
		{where}
		ORDER BY lc.end_date IS NULL, lc.end_date, lc.employee
		""",
		values,
		as_dict=True,
	)


# =============================================================================
# "Export Contract Data" button — one row per contract with what HR needs to
# draft the paper contract (mail merge into the Word template).
# =============================================================================

# Headers stay plain English on purpose (not _()): Word mail-merge fields bind to
# the header text, so it must not change with the user's language.
EXPORT_COLUMNS = [
	("Contract ID", "name"),
	("Contract Type", "contract_type"),
	("Status", "status"),
	("Start Date", "start_date"),
	("End Date", "end_date"),
	# The follow-up contract: what HR drafts next. Blank when Indefinite-term or
	# when the employee leaves on/before it would start (see Relieving Date).
	("Next Contract Type", "next_contract_type"),
	("Next Contract Start Date", "next_sign_date"),
	("Next Contract End Date", "next_end_date"),
	("Next Contract ID", "next_contract"),
	("Next Contract Status", "next_status"),
	("Relieving Date", "relieving_date"),
	("Employee ID", "employee"),
	("Full Name", "employee_name"),
	("Gender", "gender"),
	("Date of Birth", "date_of_birth"),
	("Ethnicity", "custom_ethnicity"),
	("ID Card No", "custom_id_card_no"),
	("ID Card Date of Issue", "custom_id_card_date_of_issue"),
	("ID Card Place of Issue", "custom_id_card_place_of_issue"),
	("Permanent Address", "custom_permanent_address_full"),
	("Current Address", "custom_current_address_full"),
	("Mobile", "cell_number"),
	("Designation", "designation"),
	("Designation (Vietnamese)", "custom_designation_vietnamese"),
	("Department", "department"),
	("Section", "custom_section"),
	("Group", "custom_group"),
	("Date of Joining", "date_of_joining"),
	("Social Insurance No", "custom_social_insurance_number"),
	("Tax Code", "custom_tax_code"),
	("Bank Name", "bank_name"),
	("Bank Branch", "custom_bank_branch"),
	("Bank Account No", "bank_ac_no"),
]
SALARY_COLUMN = ("Base Salary", "base_salary")
DATE_FIELDS = {
	"start_date", "end_date", "date_of_birth", "custom_id_card_date_of_issue", "date_of_joining",
	"next_sign_date", "next_end_date", "relieving_date",
}


@frappe.whitelist()
def export_contract_data(filters=None):
	"""Excel of the contracts matching the report's current filters, with the
	employee details a labor contract needs. Base Salary comes from the latest
	submitted Salary Structure Assignment effective on the contract start date,
	and is only included for users who can read SSAs."""
	frappe.only_for(EXPORT_ROLES)
	from frappe.utils.xlsxutils import make_xlsx

	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	where, values = _build_conditions(filters)
	with_salary = frappe.has_permission("Salary Structure Assignment", "read")

	# relieving_date = first day off: leaving on/before the next start = no next contract
	leaving = (
		"(emp.relieving_date IS NOT NULL AND lc.next_sign_date IS NOT NULL"
		" AND emp.relieving_date <= lc.next_sign_date)"
	)

	salary_sql = ""
	if with_salary:
		salary_sql = """,
			(SELECT ssa.base FROM `tabSalary Structure Assignment` ssa
			 WHERE ssa.employee = lc.employee AND ssa.docstatus = 1
			   AND ssa.from_date <= lc.start_date
			 ORDER BY ssa.from_date DESC LIMIT 1) AS base_salary"""

	rows = frappe.db.sql(
		f"""
		SELECT
			lc.name, lc.contract_type, lc.status, lc.start_date, lc.end_date,
			IF({leaving}, NULL, lc.next_contract_type) AS next_contract_type,
			IF({leaving}, NULL, lc.next_sign_date) AS next_sign_date,
			IF({leaving} OR IFNULL(nt.custom_period, 0) = 0, NULL,
				DATE_ADD(lc.next_sign_date, INTERVAL nt.custom_period - 1 DAY)) AS next_end_date,
			nx.name AS next_contract, nx.status AS next_status, emp.relieving_date,
			lc.employee, emp.employee_name, emp.gender, emp.date_of_birth, emp.custom_ethnicity,
			emp.custom_id_card_no, emp.custom_id_card_date_of_issue,
			emp.custom_id_card_place_of_issue, emp.custom_permanent_address_full,
			emp.custom_current_address_full, emp.cell_number, emp.designation,
			emp.custom_designation_vietnamese, emp.department, emp.custom_section,
			emp.custom_group, emp.date_of_joining, emp.custom_social_insurance_number,
			emp.custom_tax_code, emp.bank_name, emp.custom_bank_branch, emp.bank_ac_no
			{salary_sql}
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		LEFT JOIN `tabEmployment Type` nt ON nt.name = lc.next_contract_type
		LEFT JOIN `tabLabor Contract` nx ON nx.employee = lc.employee
			AND nx.contract_type = lc.next_contract_type AND nx.start_date = lc.next_sign_date
		{where}
		ORDER BY lc.start_date, lc.employee
		""",
		values,
		as_dict=True,
	)

	columns = EXPORT_COLUMNS + ([SALARY_COLUMN] if with_salary else [])

	def cell(row, field):
		value = row.get(field)
		# dd/mm/yyyy text: contracts print dates as text, and a mail merge of a
		# real Excel date falls back to the Windows locale (often mm/dd).
		if field in DATE_FIELDS:
			return getdate(value).strftime("%d/%m/%Y") if value else ""
		return value if value is not None else ""

	data = [[label for label, _field in columns]]
	data += [[cell(row, field) for _label, field in columns] for row in rows]

	xlsx = make_xlsx(data, "Labor Contracts")
	frappe.response["filename"] = f"Labor_Contract_Data_{nowdate()}.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"
