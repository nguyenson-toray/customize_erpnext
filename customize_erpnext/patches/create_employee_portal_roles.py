# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: roles of the Employee Portal (Zalo Mini App) module.

- Payroll Officer: the ONLY role that can read TIQN Payslip. HR Manager deliberately
  does not get salary data (decided 12/10/2026).
- Portal Approver: department heads who approve Mini App leave / explanations on Desk.
  Gets no DocType permission of its own - approvers see requests because they are
  shared with them. Do NOT give them `Leave Approver`: that role reads every leave
  application in the company.

pre_model_sync because the module's DocTypes ship DocPerm rows pointing at these
roles (DocPerm.role is a Link). Idempotent; assigning users is left to an admin.
"""

import frappe

ROLES = ("Payroll Officer", "Portal Approver")


def execute():
	for role in ROLES:
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1, "is_custom": 1}).insert(
				ignore_permissions=True
			)
