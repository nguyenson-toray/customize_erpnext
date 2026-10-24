# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Home screen - API_CONTRACT.md §7 `get_home` (screens 06 and 10)."""

import frappe
from frappe import _
from frappe.utils import nowdate

from customize_erpnext.api.employee_portal.auth import chat_payload, employee_payload, oa_payload
from customize_erpnext.api.employee_portal.core import access_payload, ctx, feature_enabled, fmt_date, fmt_datetime, portal_api
from customize_erpnext.api.employee_portal.notifications import latest_notification, unread_count
from customize_erpnext.employee_portal import attendance_data as ad
from customize_erpnext.employee_portal.utils import period_label, period_of_date


@portal_api(methods=("GET",))
def get_home():
	c = ctx()
	account = frappe.db.get_value("TIQN Portal Account", c.account, ["followed_oa", "oa_invite_dismissed"], as_dict=True)
	data = {
		"employee": employee_payload(c.employee),
		"access": access_payload(c),
		"today": None,
		"annual_leave": None,
		"attendance": None,
		"overtime": None,
		"latest_payslip": None,
		"notifications": None,
		"oa": oa_payload(account),
		"chat": chat_payload(),
	}

	if feature_enabled("attendance"):
		today = ad.employee_today(c.employee)
		today["date"] = fmt_date(today["date"])
		today["updated_at"] = fmt_datetime(today["updated_at"])
		data["today"] = today

		period = period_of_date(nowdate())
		s = ad.period_summary(c.employee, period)
		month = period.split("-")[1]
		data["attendance"] = {
			"period": period,
			"period_label": _("Attendance {0}", context="Portal").format(month),
			"payable_days": s["payable_days"],
			"standard_days": s["standard_days"],
			"source": s["source"],
			"provisional": s["provisional"],
		}
		if feature_enabled("overtime"):
			data["overtime"] = {"period": period, "hours": s["ot_hours"], "source": s["source"]}

	if feature_enabled("leave_view"):
		balances = ad.leave_balances(c.employee)
		for leave_type in ad.annual_leave_types():
			if leave_type in balances:
				b = balances[leave_type]
				data["annual_leave"] = {"year": int(nowdate()[:4]), "remaining": b["remaining"], "available": b["available"]}
				break

	if feature_enabled("payslip"):
		latest = frappe.get_all(
			"TIQN Payslip",
			filters={"employee": c.employee, "status": "Published"},
			fields=["period", "published_on"],
			order_by="period desc",
			limit=1,
		)
		if latest:
			data["latest_payslip"] = {
				"period": latest[0].period,
				"label": _("Payslip {0}").format(period_label(latest[0].period)),
				"published_on": fmt_date(latest[0].published_on),
				# Cache key of the payslip (1.5.0): same value as get_payslip_periods.items[].published_on.
				"published_at": fmt_datetime(latest[0].published_on),
			}

	if feature_enabled("notifications"):
		data["notifications"] = {"unread": unread_count(c.employee, c.account), "latest": latest_notification(c.employee, c.account)}
	return data
