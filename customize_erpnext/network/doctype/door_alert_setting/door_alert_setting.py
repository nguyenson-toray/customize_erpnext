# -*- coding: utf-8 -*-
# Settings of the Telegram door alerts (customize_erpnext.network.door.alerts).
# Created switched OFF with no recipients on purpose: an admin fills in the
# chats and turns it on (same rule as every alert/e-mail feature of this app).

import frappe
from frappe import _
from frappe.model.document import Document


class DoorAlertSetting(Document):
	def onload(self):
		# options of Unlock Permissions > Door (a Select filled by the form script):
		# doors are rows of a Single, not documents, so a Link field cannot point at them
		from customize_erpnext.network.biometric.machines import get_machines

		self.set_onload("doors", [
			{"device_name": d["device_name"], "enable": d["enable"]} for d in get_machines(door_only=True)
		])

	def validate(self):
		if not (1 <= (self.check_interval_minutes or 0) <= 60):
			frappe.throw(_("Check Interval (Minutes) must be between 1 and 60"))
		if self.alert_device_offline and not (1 <= (self.offline_after_minutes or 0) <= 1440):
			frappe.throw(_("Offline After (Minutes) must be between 1 and 1440"))
		if self.alert_not_locked_after_hours and not (5 <= (self.not_locked_repeat_minutes or 0) <= 720):
			frappe.throw(_("Remind Every (Minutes) must be between 5 and 720"))
		for row in self.recipients or []:
			row.chat_id = (row.chat_id or "").strip()
		self._validate_unlock_permissions()
		if self.enabled:
			if not self.get_password("bot_token", raise_exception=False):
				frappe.throw(_("Enter the Bot Token before enabling door alerts"))
			if not any(r.enabled and r.chat_id for r in self.recipients or []):
				frappe.throw(_("Add at least one enabled recipient before enabling door alerts"))

	def _validate_unlock_permissions(self):
		"""Unlock Permissions rows: Door -> Device Name (a unique Location is accepted),
		Users -> existing user IDs, normalised to "a@x, b@x"."""
		# without write access at permlevel 1 the table was just reset to the saved rows:
		# a Door Control user saving the alert settings must not be blocked by them
		if not self.has_permlevel_access_to("unlock_permissions", permission_type="write"):
			return

		from customize_erpnext.network.biometric.machines import get_machines
		from customize_erpnext.network.door.control import split_users

		doors = get_machines(door_only=True)
		by_name = {d["device_name"].lower(): d["device_name"] for d in doors}
		by_location = {}
		for d in doors:
			if d["location"]:
				by_location.setdefault(d["location"].strip().lower(), []).append(d["device_name"])

		seen = set()
		without_role = set()
		for row in self.unlock_permissions or []:
			key = (row.door or "").strip().lower()
			located = by_location.get(key) or []
			door = by_name.get(key) or (located[0] if len(located) == 1 else None)
			if not door:
				frappe.throw(
					_("Unlock Permissions row {0}: {1} is not a door controller. Use one of: {2}").format(
						row.idx, row.door, ", ".join(sorted(by_name.values()))
					)
				)
			if door in seen:
				frappe.throw(_("Unlock Permissions row {0}: {1} is listed twice").format(row.idx, door))
			seen.add(door)
			row.door = door

			users = []
			unknown = []
			for u in split_users(row.users):
				name = frappe.db.get_value("User", u, "name")
				if name:
					users.append(name)
					if "Door Control" not in frappe.get_roles(name):
						without_role.add(name)
				else:
					unknown.append(u)
			if unknown:
				frappe.throw(
					_("Unlock Permissions row {0}: user not found: {1}").format(row.idx, ", ".join(unknown))
				)
			row.users = ", ".join(users)

		if without_role:
			frappe.msgprint(
				_("These users do not have the Door Control role and cannot open /door_control yet: {0}").format(
					", ".join(sorted(without_role))
				),
				indicator="orange",
				alert=True,
			)
