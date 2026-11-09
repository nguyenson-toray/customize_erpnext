# -*- coding: utf-8 -*-
# Door watched by an ESP32 board + magnetic sensor (open / closed, no lock).
# The status fields are written by customize_erpnext.network.door.sensor.report
# with db.set_value(update_modified=False): a heartbeat every minute must not
# create a Version or touch `modified` (track_changes is off on purpose).

import frappe
from frappe import _
from frappe.model.document import Document


class DoorSensor(Document):
	def validate(self):
		from customize_erpnext.network.biometric.machines import get_machines
		from customize_erpnext.network.door.sensor import SENSOR_ID_RE

		self.sensor_id = (self.sensor_id or "").strip()
		if not SENSOR_ID_RE.match(self.sensor_id):
			frappe.throw(_("Sensor ID may only contain letters, digits, '.', '_' and '-' (at most 32)"))
		# /door_control and the alert state key doors by name: a sensor must never
		# take the name of a door controller
		taken = {m["device_name"].strip().lower() for m in get_machines(include_door=True)}
		if self.sensor_id.lower() in taken:
			frappe.throw(_("{0} is already the Device Name of a machine in Attendance Machine Setting").format(self.sensor_id))
		if not self.last_state:
			self.last_state = "unknown"
