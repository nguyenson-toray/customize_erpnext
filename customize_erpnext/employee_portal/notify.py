# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Create in-app notifications for the Mini App (TIQN Portal Notification).

In-app only. Sending Zalo OA messages is a separate, switched-off feature
(Employee Portal Settings → Send OA Messages) - never send anything outward from
here.
"""

import frappe

TARGET_SCREEN = {
	"PAYSLIP_PUBLISHED": "PAYSLIP",
	"LEAVE_APPROVED": "LEAVE",
	"LEAVE_REJECTED": "LEAVE",
	"LEAVE_CANCELLED": "LEAVE",
	"LEAVE_NEEDS_DOCUMENTS": "LEAVE",
	"EXPLANATION_APPROVED": "EXPLANATION",
	"EXPLANATION_REJECTED": "EXPLANATION",
	"OVERTIME_APPROVED": "OVERTIME",
	"GENERAL": "NONE",
}


def notify(
	employee,
	type,
	title,
	body=None,
	title_args=(),
	body_args=(),
	target_id=None,
	reference_doctype=None,
	reference_name=None,
):
	"""Notification to one employee, or several (`employee` may be a list) - still ONE row.

	`title` / `body` are ENGLISH source strings (+ format args), translated to
	Vietnamese here. The text is stored, so it must not depend on the language of
	whoever triggered it - a Desk user with English UI pressing Publish would
	otherwise send "Payslip 09/2026" to every employee."""
	if type not in TARGET_SCREEN:
		frappe.throw(f"Unknown portal notification type {type}")
	employees = [employee] if isinstance(employee, str) else list(employee or [])
	title = frappe._(title, lang="vi").format(*title_args)
	body = frappe._(body, lang="vi").format(*body_args) if body else None
	return frappe.get_doc(
		{
			"doctype": "TIQN Portal Notification",
			"audience": "Employees",
			"employees": [{"employee": e} for e in employees],
			"type": type,
			"title": title,
			"body": body,
			"target_screen": TARGET_SCREEN[type],
			"target_id": target_id,
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		}
	).insert(ignore_permissions=True)


def notify_all(type, title, body=None, title_args=(), body_args=(), target_id=None):
	"""ONE company-wide notification (audience All) instead of one row per employee.
	No per-person read state. Idempotent on (type, target_id): publishing the rest of
	a period later, or again after a withdraw, does not send it twice."""
	if type not in TARGET_SCREEN:
		frappe.throw(f"Unknown portal notification type {type}")
	existing = frappe.db.get_value("TIQN Portal Notification", {"audience": "All", "type": type, "target_id": target_id})
	if existing:
		return frappe.get_doc("TIQN Portal Notification", existing)
	return frappe.get_doc(
		{
			"doctype": "TIQN Portal Notification",
			"audience": "All",
			"type": type,
			"title": frappe._(title, lang="vi").format(*title_args),
			"body": frappe._(body, lang="vi").format(*body_args) if body else None,
			"target_screen": TARGET_SCREEN[type],
			"target_id": target_id,
		}
	).insert(ignore_permissions=True)
