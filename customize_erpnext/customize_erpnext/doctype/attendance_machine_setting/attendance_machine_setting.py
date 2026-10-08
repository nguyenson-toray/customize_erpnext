# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AttendanceMachineSetting(Document):
	def validate(self):
		self._validate_unique_machines()
		self._validate_door_controllers()

	def _validate_unique_machines(self):
		"""device_name is used as the machine identifier across all sync APIs,
		so it must be unique; duplicate IPs are almost certainly a mistake too."""
		names = set()
		ips = set()
		for row in self.machines or []:
			if row.device_name in names:
				frappe.throw(_("Duplicate Device Name: {0}").format(row.device_name))
			if row.ip_address in ips:
				frappe.throw(_("Duplicate IP Address: {0}").format(row.ip_address))
			names.add(row.device_name)
			ips.add(row.ip_address)

	def _validate_door_controllers(self):
		"""Door controllers are kept apart from attendance: a door device can never be
		the master that fingerprints are copied from."""
		for row in self.machines or []:
			if not row.is_door_control:
				continue
			if row.master_device:
				frappe.throw(
					_("Row {0}: {1} is a door controller and cannot be the Master Device").format(
						row.idx, row.device_name
					)
				)
			if row.unlock_seconds is not None and not (1 <= int(row.unlock_seconds) <= 60):
				frappe.throw(
					_("Row {0}: Unlock Seconds must be between 1 and 60").format(row.idx)
				)
