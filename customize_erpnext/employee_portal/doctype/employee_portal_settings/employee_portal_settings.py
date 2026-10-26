# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document

from customize_erpnext.employee_portal.utils import clean_id_by_oa, payslip_component_fields, strip_code_formula


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
		self.sync_payslip_lines()
		self.validate_payslip_lines()

	def onload(self):
		self.sync_payslip_lines()  # a field IT just added shows up before the next save

	def sync_payslip_lines(self):
		"""Payslip Lines = the TIQN Payslip lines in code order (IT adds / removes fields);
		CnB edits only the Mini App Label, kept per field."""
		typed = {r.payslip_field: (r.portal_label or "").strip() for r in self.payslip_lines or []}
		wanted = [(c.abbr, c.fieldname, c.name) for c in payslip_component_fields()]
		current = [(r.code, r.payslip_field, r.erp_label) for r in self.payslip_lines or []]
		if wanted == current:
			return
		self.set("payslip_lines", [])
		for code, fieldname, erp_label in wanted:
			self.append(
				"payslip_lines",
				{"code": code, "payslip_field": fieldname, "erp_label": erp_label, "portal_label": typed.get(fieldname) or None},
			)

	def validate_payslip_lines(self):
		"""The Mini App text is shown word for word: it must start with the line number."""
		for row in self.payslip_lines or []:
			row.portal_label = " ".join((row.portal_label or "").split()) or None
			if row.portal_label and not re.match(rf"^{re.escape(row.code)}(\s|$)", row.portal_label):
				frappe.throw(
					_("Payslip Lines row {0}: the Mini App Label must start with the line number, e.g. \"{1} {2}\".").format(
						row.idx, row.code, strip_code_formula(row.portal_label) or "..."
					)
				)

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
