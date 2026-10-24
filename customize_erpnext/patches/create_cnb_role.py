# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: role `CnB` (Compensation & Benefits) - the payroll team that runs the
Employee Portal (24/10/2026): payslip upload / publish, period report, notifications,
Zalo accounts, link requests and the portal settings. With System Manager it replaces
Payroll Officer and HR Manager on every Employee Portal DocType, page and report - HR
Manager deliberately does not get salary data.

pre_model_sync because those DocTypes ship DocPerm rows pointing at `CnB` (Link).
Idempotent; assigning users is left to an admin.
"""

import frappe

ROLE = "CnB"


def execute():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1, "is_custom": 1}).insert(
			ignore_permissions=True
		)
