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


def notification_payload(n, seen_on=None):
	# No per-person read state (23/10/2026): "read" = created before the user last
	# marked the list read (TIQN Portal Account.notifications_seen_on).
	return {
		"id": n.name,
		"type": n.type,
		"title": n.title,
		"body": n.body,
		"created_at": fmt_datetime(n.creation),
		"is_read": bool(seen_on and n.creation <= seen_on),
		"target": {"screen": n.target_screen or "NONE", "id": n.target_id or None},
	}


def seen_on(account):
	return frappe.db.get_value("TIQN Portal Account", account, "notifications_seen_on")


# Picked employees (Table MultiSelect) + company-wide ones. A company-wide
# PAYSLIP_PUBLISHED is shown only to employees who have a published payslip for that
# period (ONE row per period, not one per employee).
VISIBLE = """
	((n.audience = 'Employees'
	  AND EXISTS (SELECT 1 FROM `tabTIQN Portal Notification Recipient` r
	              WHERE r.parent = n.name AND r.parenttype = 'TIQN Portal Notification'
	                AND r.parentfield = 'employees' AND r.employee = %(employee)s))
	 OR (n.audience = 'All'
	     AND (n.type != 'PAYSLIP_PUBLISHED'
	          OR EXISTS (SELECT 1 FROM `tabTIQN Payslip` p
	                     WHERE p.employee = %(employee)s AND p.period = n.target_id AND p.status = 'Published'))))
"""
UNREAD = "(%(seen_on)s IS NULL OR n.creation > %(seen_on)s)"
FIELDS = "n.name, n.audience, n.type, n.title, n.body, n.creation, n.target_screen, n.target_id"


def _query(employee, seen, unread_only=False, start=0, limit=None):
	where = VISIBLE + (" AND " + UNREAD if unread_only else "")
	sql = f"SELECT {FIELDS} FROM `tabTIQN Portal Notification` n WHERE {where} ORDER BY n.creation DESC"
	if limit:
		sql += f" LIMIT {int(start)}, {int(limit)}"
	return frappe.db.sql(sql, {"employee": employee, "seen_on": seen}, as_dict=True)


def unread_count(employee, account):
	return frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabTIQN Portal Notification` n WHERE {VISIBLE} AND {UNREAD}",
		{"employee": employee, "seen_on": seen_on(account)},
	)[0][0]


def latest_notification(employee, account):
	seen = seen_on(account)
	rows = _query(employee, seen, limit=1)
	return notification_payload(rows[0], seen) if rows else None


@portal_api(methods=("GET",), feature="notifications")
def get_notifications(page=None, page_size=None, unread_only=None):
	c = ctx()
	page, page_size = paging(page, page_size)
	seen = seen_on(c.account)
	rows = _query(c.employee, seen, unread_only=cint(unread_only), start=(page - 1) * page_size, limit=page_size + 1)
	return {
		"unread": unread_count(c.employee, c.account),
		"items": [notification_payload(r, seen) for r in rows[:page_size]],
		"page": page,
		"page_size": page_size,
		"has_more": len(rows) > page_size,
	}


@portal_api(methods=("POST",), feature="notifications")
def mark_notifications_read(ids=None, all=None):
	"""Moves this user's "seen" mark up: to now (all=1), or to the newest of `ids` -
	which also marks everything older as read. Only rows this employee can see count,
	so one employee cannot affect another (the mark is per account)."""
	c = ctx()
	if cint(all):
		upto = now_datetime()
	else:
		if isinstance(ids, str):
			ids = frappe.parse_json(ids) if ids.strip().startswith("[") else [x.strip() for x in ids.split(",")]
		ids = {x for x in (ids or []) if x}
		if not ids:
			raise PortalError("VALIDATION", _("Send ids, or all=1."), field="ids")
		mine = [r.creation for r in _query(c.employee, None) if r.name in ids]
		upto = max(mine) if mine else None
	if upto:
		current = seen_on(c.account)
		if not current or upto > current:
			frappe.db.set_value("TIQN Portal Account", c.account, "notifications_seen_on", upto, update_modified=False)
	return {"unread": unread_count(c.employee, c.account)}
