# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: create the `Quiz Manager` role.

Every Employee Quiz DocType ships a DocPerm row for this role and DocPerm.role is
a Link, so the Role must exist BEFORE the model sync imports those DocTypes.
Idempotent. Assigning the role to users is left to an admin.
"""

import frappe

ROLE = "Quiz Manager"


def execute():
	if frappe.db.exists("Role", ROLE):
		return

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": ROLE,
			"desk_access": 1,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)
