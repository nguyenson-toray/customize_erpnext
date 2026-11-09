# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""pre_model_sync: create the `Door Sensor` role.

The ESP32 door sensors post their state to
customize_erpnext.network.door.sensor.report as a technical user that has this
role only. The role grants no DocType permission and no desk access (a user
holding only this role is a Website User): it can call that one endpoint and
nothing else, and it cannot open /door_control.

Runs before the model sync so a DocPerm row pointing at the role can never fail
link validation. Idempotent.
"""

import frappe

ROLE = "Door Sensor"


def execute():
	if frappe.db.exists("Role", ROLE):
		return

	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": ROLE,
			"desk_access": 0,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)
