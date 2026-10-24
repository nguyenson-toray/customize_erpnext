# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import unicodedata

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from customize_erpnext.employee_portal.utils import PHONE_FIELDS, find_employees_by_phone, phone_key

ZALO_PHONE_FIELD = PHONE_FIELDS[1]


def normalise_name(name):
	"""'  Nguyễn  Văn ĐẠT ' -> 'nguyen van dat' (accents, đ, capitals and spaces ignored)."""
	text = (name or "").replace("đ", "d").replace("Đ", "D")
	text = "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")
	return " ".join(text.lower().split())


class TIQNPortalLinkRequest(Document):
	"""A Zalo user whose phone matches no employee says "I am employee X".

	Created only by the Mini App (`auth.link_employee_request`). The employee code and
	name are NOT secret - a colleague can type them - so HR must check who really sent
	it (call the Zalo phone) before approving.

	Approve writes the Zalo phone to the employee's Zalo phone column; the next `login`
	then matches through `find_employees_by_phone` like any other employee. No second
	way of linking a Zalo account to an employee exists.
	"""

	def validate(self):
		if self.status == "Pending":
			self.set_checks()

	def onload(self):
		if self.status == "Pending":
			self.set_checks()

	def set_checks(self):
		"""name_match + the warnings HR reads before approving (recomputed on every load)."""
		employee_name = frappe.db.get_value("Employee", self.employee, "employee_name") if self.employee else None
		self.name_match = int(bool(employee_name) and normalise_name(employee_name) == normalise_name(self.full_name))
		self.warning = "\n".join(self.approval_warnings(employee_name)) or None

	def approval_warnings(self, employee_name):
		out = []
		if not self.name_match:
			out.append(_("The typed name is different from the Employee Name."))
		blocker = self.phone_owner()
		if blocker:
			out.append(_("Zalo phone {0} already belongs to {1} - this request cannot be approved.").format(self.phone, blocker))
		current = frappe.db.get_value("Employee", self.employee, ZALO_PHONE_FIELD) if self.has_zalo_phone_field() else None
		if current and phone_key(current) != phone_key(self.phone):
			out.append(_("The employee already has Zalo phone {0}. Approving replaces it.").format(current))
		others = frappe.get_all(
			"TIQN Portal Account",
			filters={"employee": self.employee, "name": ["!=", self.account or ""], "disabled": 0},
			fields=["name", "zalo_name"],
		)
		if others:
			out.append(
				_("This employee already signs in from another Zalo account: {0}.").format(
					", ".join(f"{a.zalo_name or ''} ({a.name})".strip() for a in others)
				)
			)
		pending = frappe.get_all(
			"TIQN Portal Link Request",
			filters={"employee": self.employee, "status": "Pending", "name": ["!=", self.name or ""]},
			pluck="name",
		)
		if pending:
			out.append(_("Other pending requests for this employee: {0}.").format(", ".join(pending)))
		return out

	def phone_owner(self):
		"""Another employee the Zalo phone already leads to (approving would be pointless)."""
		matches = find_employees_by_phone(self.phone) if self.phone else []
		if matches and matches[0].name != self.employee:
			return matches[0].name
		return None

	@staticmethod
	def has_zalo_phone_field():
		return frappe.get_meta("Employee").has_field(ZALO_PHONE_FIELD)

	def check_reviewable(self):
		self.check_permission("write")
		if self.status != "Pending":
			frappe.throw(_("This request is already {0}.").format(_(self.status)))

	@frappe.whitelist()
	def approve(self):
		self.check_reviewable()
		if not self.has_zalo_phone_field():
			frappe.throw(_("Employee has no field {0}.").format(ZALO_PHONE_FIELD))
		if not phone_key(self.phone):
			frappe.throw(_("This request has no Zalo phone."))
		blocker = self.phone_owner()
		if blocker:
			frappe.throw(_("Zalo phone {0} already belongs to {1}.").format(self.phone, blocker))

		employee = frappe.get_doc("Employee", self.employee)
		employee.set(ZALO_PHONE_FIELD, self.phone)
		# Approving is limited to CnB / System Manager by this DocType; the employee's own
		# permlevel rules must not make the approval half-done.
		employee.flags.ignore_permissions = True
		employee.save()

		self.set_checks()
		self.status = "Approved"
		self.reviewed_by = frappe.session.user
		self.reviewed_on = now_datetime()
		self.save()

	@frappe.whitelist()
	def reject(self, reason=None):
		self.check_reviewable()
		self.status = "Rejected"
		self.reject_reason = (reason or "").strip() or None
		self.reviewed_by = frappe.session.user
		self.reviewed_on = now_datetime()
		self.save()
