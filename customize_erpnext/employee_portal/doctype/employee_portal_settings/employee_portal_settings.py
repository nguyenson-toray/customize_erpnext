# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from customize_erpnext.employee_portal.utils import clean_id_by_oa


class EmployeePortalSettings(Document):
	def validate(self):
		if self.min_client_version and not re.match(r"^\d+\.\d+\.\d+$", self.min_client_version.strip()):
			frappe.throw(_("Minimum Mini App Version must look like 1.0.0"))
		if self.expected_pay_day and not 1 <= self.expected_pay_day <= 31:
			frappe.throw(_("Pay Day of Month must be between 1 and 31"))
		for field in ("read_only_days", "session_days", "max_files", "max_file_size_mb"):
			if (self.get(field) or 0) < 0:
				frappe.throw(_("{0} cannot be negative").format(self.meta.get_label(field)))
		if not (self.session_days or 0) >= 1:
			# 0 would end every new session the moment it is created.
			frappe.throw(_("{0} must be at least 1").format(self.meta.get_label("session_days")))
		self.clear_dependent_features()
		self.cb_chat_id_by_oa = clean_id_by_oa(self.cb_chat_id_by_oa)

	# feature -> features that only exist inside its screens
	FEATURE_DEPENDENTS = {
		"feature_attendance": ("feature_overtime", "feature_explanation_create"),
		"feature_leave_view": ("feature_leave_create",),
	}

	def clear_dependent_features(self):
		"""The form hides a dependent checkbox when its parent is off, but the value would
		stay 1 and the API (`features`) would still report it on."""
		for parent, dependents in self.FEATURE_DEPENDENTS.items():
			if not self.get(parent):
				for field in dependents:
					self.set(field, 0)
