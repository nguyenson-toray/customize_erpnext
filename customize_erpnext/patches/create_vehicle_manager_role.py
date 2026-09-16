# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: create the `Vehicle Manager` role.

Runs BEFORE the model sync because every TIQN Vehicle Management DocType ships a
DocPerm row pointing at this role, and DocPerm.role is a Link - a missing Role
would make the very first `bench migrate` of this module fail on link validation.

Idempotent. Assigning the role to real users is left to an admin on purpose.
"""

import frappe

ROLE = "Vehicle Manager"


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
