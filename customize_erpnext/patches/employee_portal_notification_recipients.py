# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""TIQN Portal Notification: single `employee` + per-person `is_read` -> audience
`Employees` with a Table MultiSelect of recipients, no per-person read state
(23/10/2026). post_model_sync, idempotent.

Old rows (audience "Employee", the `employee` column Frappe leaves in the table after
the field is removed) become audience "Employees" with that one recipient.
"""

import frappe

DT = "TIQN Portal Notification"
CHILD = "TIQN Portal Notification Recipient"


def execute():
	frappe.reload_doc("employee_portal", "doctype", "tiqn_portal_notification_recipient")
	frappe.reload_doc("employee_portal", "doctype", "tiqn_portal_notification")
	has_employee_column = "employee" in frappe.db.get_table_columns(DT)
	rows = frappe.db.sql(
		f"SELECT name{', employee' if has_employee_column else ''} FROM `tab{DT}` "
		"WHERE IFNULL(audience, '') NOT IN ('All', 'Employees')",
		as_dict=True,
	)
	for r in rows:
		employee = r.get("employee")
		if employee and not frappe.db.exists(CHILD, {"parent": r.name, "employee": employee}):
			child = frappe.get_doc(
				{
					"doctype": CHILD,
					"parent": r.name,
					"parenttype": DT,
					"parentfield": "employees",
					"employee": employee,
					"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
					"idx": 1,
				}
			)
			child.db_insert()
		frappe.db.set_value(DT, r.name, "audience", "Employees" if employee else "All", update_modified=False)
