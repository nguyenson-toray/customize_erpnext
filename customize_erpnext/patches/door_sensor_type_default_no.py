# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: Sensor Type of door controllers defaults to NO (10/10/2026).

The doors use ZKTeco LB-35 locks whose bolt sensor is NO/COM. Rows that are
door controllers and still have no Sensor Type (empty / "None") get "NO".
Attendance machines are not touched. Nothing changes in behaviour until
Door Alert Setting → Use Lock Sensor is ticked. Idempotent.
"""

import frappe


def execute():
	frappe.db.sql(
		"""update `tabAttendance Machine Detail`
		set sensor_type = 'NO'
		where is_door_control = 1 and ifnull(sensor_type, '') in ('', 'None')"""
	)
