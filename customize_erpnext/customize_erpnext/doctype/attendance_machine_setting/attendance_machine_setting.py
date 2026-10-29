# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class AttendanceMachineSetting(Document):
	def validate(self):
		self._validate_unique_machines()
		self._validate_door_controllers()
		self._validate_comm_passwords()
		self._validate_error_email()
		self._validate_peak_times()

	def on_update(self):
		self._rename_doors_in_unlock_permissions()

	def _rename_doors_in_unlock_permissions(self):
		"""Door Alert Setting > Unlock Permissions names doors by Device Name: follow a
		rename, otherwise the renamed door would silently be unlockable by everyone."""
		before = self.get_doc_before_save()
		if not before:
			return
		old = {r.name: r.device_name for r in before.machines or []}
		renamed = {
			old[r.name]: r.device_name
			for r in self.machines or []
			if r.name in old and old[r.name] != r.device_name
		}
		if not renamed:
			return
		for old_name, new_name in renamed.items():
			frappe.db.sql(
				"""update `tabDoor Unlock Permission` set door = %s
				where parenttype = 'Door Alert Setting' and door = %s""",
				(new_name, old_name),
			)
		frappe.clear_document_cache("Door Alert Setting", "Door Alert Setting")

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

	def _validate_comm_passwords(self):
		"""ZKTeco comm key: an integer 0–999999 (pyzk packs it as a number)."""
		for row in self.machines or []:
			value = (row.comm_password or "").strip()
			row.comm_password = value or None
			if value and not (value.isdigit() and int(value) <= 999999):
				frappe.throw(
					_("Row {0}: Communication Password must be digits only (0–999999)").format(row.idx)
				)

	def _validate_door_controllers(self):
		"""Door-controller fields of each row."""
		for row in self.machines or []:
			if not row.is_door_control:
				continue
			if row.unlock_seconds is not None and not (1 <= int(row.unlock_seconds) <= 60):
				frappe.throw(
					_("Row {0}: Unlock Seconds must be between 1 and 60").format(row.idx)
				)

	def _validate_error_email(self):
		if not self.send_error_email:
			return
		for email in (self.error_email_recipients or "").split():
			if not frappe.utils.validate_email_address(email.strip(",; ")):
				frappe.throw(_("Invalid email address in Recipients: {0}").format(email))
		if cint(self.error_email_cooldown_minutes) < 1:
			frappe.throw(_("Cooldown (Minutes) must be at least 1"))

	def _validate_peak_times(self):
		from customize_erpnext.customize_erpnext.doctype.attendance_calculation_setting.attendance_calculation_setting import (
			parse_peak_times,
		)

		parse_peak_times(self.peak_times)  # throws on a bad HH:MM list
		if self.peak_times and not (1 <= cint(self.peak_window_minutes) <= 120):
			frappe.throw(_("Peak Window Minutes must be between 1 and 120"))
