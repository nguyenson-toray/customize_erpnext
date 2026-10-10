# -*- coding: utf-8 -*-
# Settings of the Telegram door alerts (customize_erpnext.api.door_alerts).
# Created switched OFF with no recipients on purpose: an admin fills in the
# chats and turns it on (same rule as every alert/e-mail feature of this app).

import frappe
from frappe import _
from frappe.model.document import Document


class DoorAlertSetting(Document):
	def validate(self):
		if not (1 <= (self.check_interval_minutes or 0) <= 60):
			frappe.throw(_("Check Interval (Minutes) must be between 1 and 60"))
		if self.alert_device_offline and not (1 <= (self.offline_after_minutes or 0) <= 1440):
			frappe.throw(_("Offline After (Minutes) must be between 1 and 1440"))
		if self.alert_not_locked_after_hours and not (5 <= (self.not_locked_repeat_minutes or 0) <= 720):
			frappe.throw(_("Remind Every (Minutes) must be between 5 and 720"))
		for row in self.recipients or []:
			row.chat_id = (row.chat_id or "").strip()
		if self.enabled:
			if not self.get_password("bot_token", raise_exception=False):
				frappe.throw(_("Enter the Bot Token before enabling door alerts"))
			if not any(r.enabled and r.chat_id for r in self.recipients or []):
				frappe.throw(_("Add at least one enabled recipient before enabling door alerts"))
