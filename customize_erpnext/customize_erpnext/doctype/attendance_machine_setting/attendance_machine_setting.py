# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class AttendanceMachineSetting(Document):
	def validate(self):
		self._validate_unique_machines()

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
