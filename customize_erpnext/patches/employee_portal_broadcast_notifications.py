# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Payslip notifications: one row per employee -> ONE company-wide row per period
(TIQN Portal Notification.audience = All, 23/10/2026). post_model_sync, idempotent.

Per-employee PAYSLIP_PUBLISHED rows are replaced by one "All" row per period that still
has a published payslip (kept at the earliest creation time, so it is not shown as new
again); the per-employee rows are deleted. Other types stay per employee.
"""

import frappe

DT = "TIQN Portal Notification"


def execute():
	frappe.reload_doc("employee_portal", "doctype", "tiqn_portal_notification")
	frappe.db.sql(f"UPDATE `tab{DT}` SET audience = 'Employee' WHERE IFNULL(audience, '') = ''")
	rows = frappe.db.sql(
		f"""
		SELECT target_id, MIN(creation) AS first_on, MAX(title) AS title, MAX(body) AS body
		FROM `tab{DT}`
		WHERE audience = 'Employee' AND type = 'PAYSLIP_PUBLISHED'
		GROUP BY target_id
		""",
		as_dict=True,
	)
	for r in rows:
		has_published = frappe.db.exists("TIQN Payslip", {"period": r.target_id, "status": "Published"})
		if has_published and not frappe.db.exists(DT, {"audience": "All", "type": "PAYSLIP_PUBLISHED", "target_id": r.target_id}):
			doc = frappe.get_doc(
				{
					"doctype": DT,
					"audience": "All",
					"type": "PAYSLIP_PUBLISHED",
					"title": r.title,
					"body": r.body,
					"target_screen": "PAYSLIP",
					"target_id": r.target_id,
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value(DT, doc.name, {"creation": r.first_on, "modified": r.first_on}, update_modified=False)
		frappe.db.delete(DT, {"audience": "Employee", "type": "PAYSLIP_PUBLISHED", "target_id": r.target_id})
