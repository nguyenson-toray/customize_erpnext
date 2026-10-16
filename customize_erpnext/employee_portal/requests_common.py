# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Shared rules for leave applications and attendance explanations in the Mini App."""

import frappe
from frappe import _
from frappe.utils import cint

from customize_erpnext.employee_portal.utils import designation_label, initials

# D9 (12/10/2026): what an employee may create from the Mini App. Everything else
# (maternity, convalescence, other paid leave, compensatory leave) is entered by HR.
ALLOWED_LEAVE_TYPES = (
	"Phép năm/ Annual leave",
	"Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau",
	"Nghỉ hưởng BHXH/ Social insurance leave - Con ốm",
	"Nghỉ không lương/ Unpaid leave",
	"Nghỉ hưởng lương/ Paid leave - Hỉ sự",
	"Nghỉ hưởng lương/ Paid leave - Ma chay",
)
# Leave types that take medical documents (screens 12b / 13b).
DOCUMENT_LEAVE_TYPES = (
	"Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau",
	"Nghỉ hưởng BHXH/ Social insurance leave - Con ốm",
)

STATUS_LABELS = {
	"PENDING": "Pending Approval",
	"APPROVED": "Approved",
	"REJECTED": "Rejected",
	"CANCELLED": "Cancelled",
}


def status_label(status):
	return _(STATUS_LABELS[status], context="Portal")


def leave_status(status, docstatus):
	if cint(docstatus) == 2 or status == "Cancelled":
		return "CANCELLED"
	return {"Approved": "APPROVED", "Rejected": "REJECTED"}.get(status, "PENDING")


def person(user):
	"""Approver card: full name, initials, designation (from the Employee linked to the user)."""
	if not user:
		return None
	emp = frappe.db.get_value("Employee", {"user_id": user}, ["employee_name", "designation"], as_dict=True)
	full_name = (emp and emp.employee_name) or frappe.utils.get_fullname(user)
	return {
		"full_name": full_name,
		"initials": initials(full_name),
		"designation": designation_label(emp.designation) if emp else None,
	}


def request_blocker(employee, read_only, feature=None):
	"""Why this employee cannot send a leave application / explanation right now, or None.

	D12: no leave approver, or an approver without an enabled ERP user -> blocked.
	"""
	from customize_erpnext.api.employee_portal.core import feature_enabled

	if read_only:
		return {"code": "READ_ONLY", "message": _("Your account is in view-only mode.")}
	if feature and not feature_enabled(feature):
		return {"code": "FEATURE_DISABLED", "message": _("This feature is currently turned off.")}
	approver = frappe.db.get_value("Employee", employee, "leave_approver")
	if not approver:
		return {
			"code": "NO_APPROVER",
			"message": _("You do not have an approver in your employee record yet. Please contact the HR department."),
		}
	if not frappe.db.get_value("User", approver, "enabled"):
		return {
			"code": "APPROVER_NO_USER",
			"message": _("Your approver does not have an active ERP account yet. Please contact the HR department."),
		}
	return None
