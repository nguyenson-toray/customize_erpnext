# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: create the `Door Control` role.

Runs BEFORE the model sync because Door Control Action and Door Access Log ship a
DocPerm row pointing at this role, and DocPerm.role is a Link - a missing Role
would make the first `bench migrate` fail on link validation.

Idempotent. The role is assigned to nobody on purpose: out of the box only
Administrator (who implicitly has every role) can open /door_control.
"""

import frappe

ROLE = "Door Control"


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
