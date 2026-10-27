# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from customize_erpnext.employee_portal.utils import (
	employee_access,
	find_employees_by_phone,
	is_review_phone,
	local_phone,
)


class TIQNPortalAccount(Document):
	"""One Zalo account of the employee portal Mini App.

	Created by `login` when someone opens the app, or by HR by hand. Rows without an
	employee are users whose phone is unknown (NO_PHONE) or matched nobody (NOT_FOUND)
	- kept so HR can see who is waiting and assign the phone.

	`phone` has two writers:
	- `login` with a Zalo phone token (flags.from_login, phone_source = Zalo);
	- HR on the form (phone_source = Manual). An HR-assigned phone lets this Zalo user
	  read that employee's payslips, so it must match an employee and every open
	  session is ended when it changes.

	Disabling keeps out people outside the company and people who left too long ago:
	a NEW account starts disabled (`auto_disabled` = 1) unless its phone matches an
	employee who may use the portal (Active, or Left but still inside the read-only
	window). It unlocks itself once that becomes true; a hand-set Disabled never does.
	A Zalo reviewer (Settings > Zalo App Review, phone confirmed by Zalo) counts as
	allowed too - their session only ever sees sample data.
	"""

	def validate(self):
		self.zalo_user_id = (self.zalo_user_id or "").strip()
		if not self.zalo_user_id:
			frappe.throw(_("Zalo User ID is required"))
		if self.phone:
			normalised = local_phone(self.phone)
			if not normalised:
				frappe.throw(_("Phone {0} is not a valid mobile number.").format(self.phone))
			self.phone = normalised
		if not self.flags.from_login and (self.is_new() or self.has_value_changed("phone")):
			self.set_phone_by_hr()
		self.apply_auto_disable()

	def apply_auto_disable(self):
		"""`employee` must already be resolved from `phone` (set_phone_by_hr / complete_login)."""
		if self.is_new() and not self.disabled and not self.employee_may_sign_in():
			self.disabled = 1
			self.auto_disabled = 1
		elif self.auto_disabled and self.employee_may_sign_in():
			self.disabled = 0
		if not self.disabled:
			self.auto_disabled = 0

	def employee_may_sign_in(self):
		if not self.employee:
			return self.phone_source == "Zalo" and is_review_phone(self.phone)
		row = frappe.db.get_value("Employee", self.employee, ["status", "relieving_date"], as_dict=True)
		return bool(row) and employee_access(row)[0] in ("ACTIVE", "READ_ONLY")

	def set_phone_by_hr(self):
		if not self.phone:
			self.employee = None
			self.phone_source = None
			return
		matches = find_employees_by_phone(self.phone)
		if not matches:
			frappe.throw(_("Phone {0} does not match the Cell Number of any employee.").format(self.phone))
		self.employee = matches[0].name
		self.phone_source = "Manual"
		if len(matches) > 1:
			frappe.msgprint(
				_("This phone belongs to {0}. The newest code, {1}, will be used.").format(
					", ".join(m.name for m in matches), matches[0].name
				),
				alert=True,
			)

	def on_update(self):
		if self.disabled and self.has_value_changed("disabled"):
			self.revoke_sessions("DISABLED")
		elif self.has_value_changed("phone") and not self.flags.from_login:
			self.revoke_sessions("PHONE_CHANGED")

	def revoke_sessions(self, reason):
		for name in frappe.get_all("TIQN Portal Session", {"account": self.name, "revoked": 0}, pluck="name"):
			frappe.db.set_value(
				"TIQN Portal Session",
				name,
				{"revoked": 1, "revoked_reason": reason, "revoked_on": now_datetime()},
				update_modified=False,
			)
