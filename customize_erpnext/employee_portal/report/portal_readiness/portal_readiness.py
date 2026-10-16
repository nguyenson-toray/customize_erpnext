# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""What HR must clean up before employees can use the Zalo Mini App.

One row per (issue, employee). Active employees only, except "Phone Not Found",
which lists Zalo logins whose phone matched no employee at all.
"""

from collections import defaultdict

import frappe
from frappe import _

from customize_erpnext.employee_portal.utils import mask_phone, phone_key


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = []
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name", "cell_number", "custom_section", "custom_group", "leave_approver", "date_of_joining"],
		order_by="name",
	)

	def add(issue, e, detail):
		rows.append(
			{
				"issue": _(issue),
				"employee": e.get("name"),
				"employee_name": e.get("employee_name"),
				"section": e.get("custom_section"),
				"group": e.get("custom_group"),
				"phone": e.get("cell_number"),
				"detail": detail,
			}
		)

	by_key = defaultdict(list)
	for e in employees:
		key = phone_key(e.cell_number)
		if not key:
			add("No Phone", e, _("Cell Number is empty or too short - this employee cannot sign in."))
		else:
			by_key[key].append(e)

	for group in by_key.values():
		if len(group) < 2:
			continue
		group.sort(key=lambda x: (str(x.date_of_joining or ""), x.name), reverse=True)
		winner = group[0].name
		for e in group:
			if e.name != winner:
				add(
					"Shared Phone",
					e,
					_("Same phone as {0}. Only {1} (newer code) can sign in until the number is corrected.").format(
						", ".join(x.name for x in group if x.name != e.name), winner
					),
				)

	approvers = {e.leave_approver for e in employees if e.leave_approver}
	approver_ok = {
		u.name
		for u in frappe.get_all("User", filters={"name": ["in", list(approvers) or [""]], "enabled": 1}, fields=["name"])
	}
	for e in employees:
		if not e.leave_approver:
			add("No Leave Approver", e, _("Cannot send leave applications or explanations from the Mini App."))
		elif e.leave_approver not in approver_ok:
			add("Approver Cannot Log In", e, _("Leave Approver {0} has no enabled ERP user.").format(e.leave_approver))

	signed_in = set(frappe.get_all("TIQN Portal Account", filters={"employee": ["is", "set"]}, pluck="employee"))
	for e in employees:
		if e.name not in signed_in and phone_key(e.cell_number):
			add("Never Signed In", e, "")

	waiting = {
		"NO_PHONE": ("Waiting for Phone", _("Zalo ID {0} signed in on {1} without a phone. Open the account and assign the employee's phone.")),
		"NOT_FOUND": ("Phone Not Found", _("Zalo ID {0} signed in on {1} with {2}, which matches no employee.")),
	}
	for a in frappe.get_all(
		"TIQN Portal Account",
		filters={"last_result": ["in", list(waiting)]},
		fields=["name", "phone", "last_login", "last_result"],
		order_by="last_login desc",
	):
		issue, text = waiting[a.last_result]
		rows.append(
			{
				"issue": _(issue),
				"employee": None,
				"employee_name": None,
				"section": None,
				"group": None,
				"phone": a.phone,
				"zalo_account": a.name,
				"detail": text.format(a.name, frappe.utils.format_datetime(a.last_login), mask_phone(a.phone)),
			}
		)

	if filters.issue:
		rows = [r for r in rows if r["issue"] == _(filters.issue)]

	columns = [
		{"fieldname": "issue", "label": _("Issue"), "fieldtype": "Data", "width": 170},
		{"fieldname": "employee", "label": _("Employee"), "fieldtype": "Link", "options": "Employee", "width": 110},
		{"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "section", "label": _("Section"), "fieldtype": "Data", "width": 110},
		{"fieldname": "group", "label": _("Group"), "fieldtype": "Data", "width": 110},
		{"fieldname": "phone", "label": _("Phone"), "fieldtype": "Data", "width": 120},
		{"fieldname": "zalo_account", "label": _("Zalo Account"), "fieldtype": "Link", "options": "TIQN Portal Account", "width": 170},
		{"fieldname": "detail", "label": _("Detail"), "fieldtype": "Data", "width": 420},
	]
	counts = defaultdict(int)
	for r in rows:
		counts[r["issue"]] += 1
	summary = [{"label": k, "value": v, "indicator": "orange"} for k, v in counts.items()]
	return columns, rows, None, None, summary
