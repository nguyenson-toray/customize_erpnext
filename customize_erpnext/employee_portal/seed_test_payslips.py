# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""FAKE payslips for the Mini App test team, on the production site.

Numbers are invented (consistent with the payroll formulas so the screen looks
real) and every row carries import_batch "TEST-SEED". Remove them all with purge()
BEFORE the Mini App is opened to the whole company.

    bench --site erp.tiqn.local execute customize_erpnext.employee_portal.seed_test_payslips.execute
    bench --site erp.tiqn.local execute customize_erpnext.employee_portal.seed_test_payslips.verify
    bench --site erp.tiqn.local execute customize_erpnext.employee_portal.seed_test_payslips.purge

Test team decided 12/10/2026: TIQN-0148, TIQN-1405.
"""

import frappe
from frappe.utils import now_datetime, today

from customize_erpnext.employee_portal.notify import notify
from customize_erpnext.employee_portal.utils import period_label, period_of_date, shift_period

BATCH = "TEST-SEED"
EMPLOYEES = ("TIQN-0148", "TIQN-1405")


def _fake_amounts(employee, period):
	"""Deterministic per (employee, period); c=a+b, f=c+d+e, j=f-g+h+i hold exactly."""
	seed = sum(ord(ch) for ch in employee + period)
	basic = 7_000_000 + (seed % 7) * 500_000
	ot_normal = 6 + seed % 9 * 0.5
	ot_weekend = (seed % 3) * 4
	ot_holiday = 0
	hourly = round(basic / 26 / 8)
	ot_money = round(hourly * (ot_normal * 1.5 + ot_weekend * 2 + ot_holiday * 3))
	a = {
		"1": basic,
		"1.1": 26,
		"1.2": 26 - seed % 2,
		"2": ot_money,
		"2.1": ot_normal,
		"2.2": ot_weekend,
		"2.3": ot_holiday,
		"3.2": 500_000,
		"3.3": 0,
		"3.4": 0,
		"3.5": 300_000,
		"3.6": 200_000,
		"3.7": 0,
		"3.8": 150_000 if seed % 2 else 0,
		"3.9": 0,
		"3.10": 0,
		"4.1": 500_000 if seed % 4 else 0,
		"4.2": 0,
		"4.3": 300_000,
		"4.4": 0,
		"4.5": 0,
		"4.6": 0,
		"4.7": 0,
		"6.1": round(basic * 0.08),
		"6.2": round(basic * 0.015),
		"6.3": round(basic * 0.01),
		"6.4": min(round(basic * 0.01), 234_000),
		"6.5": 0,
		"6.6": 0,
		"7.1": 650_000,
		"7.2": 0,
		"7.3": 0,
		"7.4": 0,
		"7.5": 0,
		"7.6": 0,
		"7.7": 0,
		"8": 150_000 if seed % 5 == 0 else 0,
	}
	a["3"] = a["1"] + a["2"]
	a["3.1"] = sum(a[f"3.{i}"] for i in range(2, 11))
	a["4"] = sum(a[f"4.{i}"] for i in range(1, 8))
	a["5"] = a["3"] + a["3.1"] + a["4"]
	a["6"] = sum(a[f"6.{i}"] for i in range(1, 7))
	a["7"] = sum(a[f"7.{i}"] for i in range(1, 8))
	a["9"] = a["5"] - a["6"] + a["7"] + a["8"]
	return a


def _components():
	return frappe.get_all(
		"Salary Component",
		filters={"custom_portal_section": ["not in", ["", "Hidden"]]},
		fields=["name", "salary_component_abbr"],
	)


def execute(employees=EMPLOYEES, periods=None, publish=1):
	"""Create (or replace) the TEST payslips. Default periods: the last 3 ended ones."""
	if isinstance(employees, str):
		employees = [e.strip() for e in employees.split(",") if e.strip()]
	last_ended = shift_period(period_of_date(today()), -1)
	periods = periods or [shift_period(last_ended, -i) for i in (2, 1, 0)]
	if isinstance(periods, str):
		periods = [p.strip() for p in periods.split(",") if p.strip()]
	components = _components()
	created = []
	for employee in employees:
		emp = frappe.db.get_value(
			"Employee", employee, ["employee_name", "department", "custom_section", "custom_group"], as_dict=True
		)
		if not emp:
			frappe.throw(f"Employee {employee} not found")
		for period in periods:
			existing = frappe.db.get_value("TIQN Payslip", {"employee": employee, "period": period}, ["name", "import_batch"], as_dict=True)
			if existing and existing.import_batch != BATCH:
				print(f"skip {employee} {period}: a REAL payslip exists ({existing.name})")
				continue
			if existing:
				frappe.delete_doc("TIQN Payslip", existing.name, ignore_permissions=True, force=True)
			amounts = _fake_amounts(employee, period)
			doc = frappe.get_doc(
				{
					"doctype": "TIQN Payslip",
					"employee": employee,
					"employee_name": emp.employee_name,
					"department": (emp.department or "").replace(" - TIQN", ""),
					"section": emp.custom_section,
					"group": emp.custom_group,
					"period": period,
					"status": "Draft",
					"import_batch": BATCH,
					"details": [
						{"salary_component": c.name, "abbr": c.salary_component_abbr, "amount": amounts.get(str(c.salary_component_abbr), 0)}
						for c in components
					],
				}
			)
			doc.insert(ignore_permissions=True)
			if int(publish):
				doc.status = "Published"
				doc.published_on = now_datetime()
				doc.published_by = frappe.session.user
				doc.save(ignore_permissions=True)
				notify(
					employee,
					"PAYSLIP_PUBLISHED",
					"Payslip {0}",
					"has been published",
					title_args=(period_label(period),),
					target_id=period,
					reference_doctype="TIQN Payslip",
					reference_name=doc.name,
				)
			created.append(doc.name)
	frappe.db.commit()
	print(f"created {len(created)}: {', '.join(created)}")
	return created


def purge():
	"""Delete every TEST payslip, its view log and its notifications."""
	names = frappe.get_all("TIQN Payslip", filters={"import_batch": BATCH}, pluck="name")
	for name in names:
		frappe.db.delete("TIQN Payslip View Log", {"payslip": name})
		frappe.db.delete("TIQN Portal Notification", {"reference_doctype": "TIQN Payslip", "reference_name": name})
		frappe.delete_doc("TIQN Payslip", name, ignore_permissions=True, force=True)
	frappe.db.commit()
	left = frappe.db.count("TIQN Payslip", {"import_batch": BATCH})
	print(f"deleted {len(names)} TEST payslips; remaining {left}")
	return len(names)


def verify():
	"""Every TEST payslip satisfies the payroll formulas and is visible as configured."""
	from customize_erpnext.api.employee_portal.payslip import build_payslip_payload

	problems = []
	for name in frappe.get_all("TIQN Payslip", filters={"import_batch": BATCH}, pluck="name"):
		doc = frappe.get_doc("TIQN Payslip", name)
		a = {d.abbr: d.amount for d in doc.details}
		if round(a["9"]) != round(a["5"] - a["6"] + a["7"] + a["8"]):
			problems.append(f"{name}: 9 != 5-6+7+8")
		payload = build_payslip_payload(doc, include_zero=False)
		earnings = next((s for s in payload["sections"] if s["key"] == "EARNINGS"), None)
		if not earnings or earnings["total"] != round(a["5"]):
			problems.append(f"{name}: EARNINGS total != component 5")
		if payload["net_pay"] != round(a["9"]):
			problems.append(f"{name}: net_pay != component 9")
	print("OK" if not problems else "\n".join(problems))
	return problems
