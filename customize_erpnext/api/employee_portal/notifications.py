# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""In-app notifications - API_CONTRACT.md §7."""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from customize_erpnext.api.employee_portal.core import PortalError, ctx, fmt_datetime, portal_api

MAX_PAGE_SIZE = 100


def paging(page, page_size):
	page = max(cint(page) or 1, 1)
	page_size = min(max(cint(page_size) or 20, 1), MAX_PAGE_SIZE)
	return page, page_size


def notification_payload(n):
	return {
		"id": n.name,
		"type": n.type,
		"title": n.title,
		"body": n.body,
		"created_at": fmt_datetime(n.creation),
		"is_read": bool(n.is_read),
		"target": {"screen": n.target_screen or "NONE", "id": n.target_id or None},
	}


def unread_count(employee):
	return frappe.db.count("TIQN Portal Notification", {"employee": employee, "is_read": 0})


def latest_notification(employee):
	rows = frappe.get_all(
		"TIQN Portal Notification",
		filters={"employee": employee},
		fields=["name", "type", "title", "body", "creation", "is_read", "target_screen", "target_id"],
		order_by="creation desc",
		limit=1,
	)
	return notification_payload(rows[0]) if rows else None


@portal_api(methods=("GET",), feature="notifications")
def get_notifications(page=None, page_size=None, unread_only=None):
	employee = ctx().employee
	page, page_size = paging(page, page_size)
	filters = {"employee": employee}
	if cint(unread_only):
		filters["is_read"] = 0
	rows = frappe.get_all(
		"TIQN Portal Notification",
		filters=filters,
		fields=["name", "type", "title", "body", "creation", "is_read", "target_screen", "target_id"],
		order_by="creation desc",
		start=(page - 1) * page_size,
		page_length=page_size + 1,
	)
	return {
		"unread": unread_count(employee),
		"items": [notification_payload(r) for r in rows[:page_size]],
		"page": page,
		"page_size": page_size,
		"has_more": len(rows) > page_size,
	}


@portal_api(methods=("POST",), feature="notifications")
def mark_notifications_read(ids=None, all=None):
	employee = ctx().employee
	filters = {"employee": employee, "is_read": 0}
	if not cint(all):
		if isinstance(ids, str):
			ids = frappe.parse_json(ids) if ids.strip().startswith("[") else [x.strip() for x in ids.split(",")]
		ids = [x for x in (ids or []) if x]
		if not ids:
			raise PortalError("VALIDATION", _("Send ids, or all=1."), field="ids")
		filters["name"] = ["in", ids]
	# Filtering by employee is what keeps one employee from touching another's rows.
	for name in frappe.get_all("TIQN Portal Notification", filters=filters, pluck="name"):
		frappe.db.set_value(
			"TIQN Portal Notification", name, {"is_read": 1, "read_on": now_datetime()}, update_modified=False
		)
	return {"unread": unread_count(employee)}
