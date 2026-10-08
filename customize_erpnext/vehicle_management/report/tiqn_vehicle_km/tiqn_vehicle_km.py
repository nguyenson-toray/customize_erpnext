# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Vehicle KM report - the sheet TIQN pays the transport partner from.

Vehicles and drivers belong to a partner company; TIQN is billed for the actual
kilometres of each trip, so `billable_km` (km_end - km_start) is the number that
matters and everything here is arranged around it.

Being a standard Frappe report buys the filters, the column picker, the chart and
the native Excel/CSV export for free - no separate endpoint needed.
"""

import frappe
from frappe import _
from frappe.utils import flt

# Reused rather than re-rolled: a Frappe Time column comes back as a timedelta
# whose str() is "6:00:00" - no leading zero - so naive slicing yields "6:00:".
from customize_erpnext.api.vehicle_management import _fmt_time

STATUS_ORDER = ("completed", "in_progress", "scheduled", "confirmed", "cancelled")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)

	rows = _get_rows(filters)
	columns = _get_columns()

	# skip_total_row=1 (the 6th return value). Frappe's add_total_row() sums EVERY
	# numeric column with no way to opt one out, which would print a total of the
	# odometer readings - adding up km_start across trips is meaningless and looks
	# like a real number. The figures that do add up live in the summary cards.
	return columns, rows, None, _get_chart(rows), _get_summary(rows), 1


def _validate(filters):
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("From Date and To Date are required"))
	if filters.from_date > filters.to_date:
		frappe.throw(_("From Date must be on or before To Date"))


def _get_columns():
	return [
		{"label": _("Date"), "fieldname": "trip_date", "fieldtype": "Date", "width": 95},
		{"label": _("Trip"), "fieldname": "name", "fieldtype": "Link", "options": "TIQN Vehicle Trip", "width": 165},
		{"label": _("Vehicle"), "fieldname": "vehicle", "fieldtype": "Link", "options": "TIQN Vehicle", "width": 120},
		{"label": _("License Plate"), "fieldname": "license_plate", "fieldtype": "Data", "width": 110},
		{"label": _("Depart"), "fieldname": "depart_time", "fieldtype": "Data", "width": 70},
		{"label": _("From"), "fieldname": "from_location", "fieldtype": "Data", "width": 170},
		{"label": _("To"), "fieldname": "to_location", "fieldtype": "Data", "width": 170},
		{"label": _("KM Start"), "fieldname": "km_start", "fieldtype": "Float", "precision": 1, "width": 95},
		{"label": _("KM End"), "fieldname": "km_end", "fieldtype": "Float", "precision": 1, "width": 95},
		{"label": _("Billable KM"), "fieldname": "billable_km", "fieldtype": "Float", "precision": 1, "width": 110},
		{"label": _("Additional Cost"), "fieldname": "additional_cost", "fieldtype": "Currency", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Type"), "fieldname": "trip_type", "fieldtype": "Data", "width": 90},
		{"label": _("Notes"), "fieldname": "notes", "fieldtype": "Data", "width": 220},
	]


def _get_rows(filters):
	conditions = {"trip_date": ("between", [filters.from_date, filters.to_date])}
	if filters.vehicle:
		conditions["vehicle"] = filters.vehicle
	if filters.status:
		conditions["status"] = filters.status

	trips = frappe.get_all(
		"TIQN Vehicle Trip",
		filters=conditions,
		fields=[
			"name", "trip_date", "depart_time", "vehicle",
			"from_location", "to_location", "km_start", "km_end", "total_km",
			"additional_cost", "status", "trip_type", "notes", "checkout_notes",
		],
		order_by="trip_date asc, depart_time asc, creation asc",
		limit_page_length=0,
	)
	if not trips:
		return []

	plates = {
		v.name: v.license_plate
		for v in frappe.get_all(
			"TIQN Vehicle",
			filters={"name": ("in", list({t.vehicle for t in trips if t.vehicle}))},
			fields=["name", "license_plate"],
			limit_page_length=0,
		)
	}

	for trip in trips:
		trip["license_plate"] = plates.get(trip.vehicle)
		# Recomputed rather than trusting total_km: this figure is invoiced, so it
		# is worth deriving from the two readings that were actually recorded.
		trip["billable_km"] = flt(trip.km_end) - flt(trip.km_start) if flt(trip.km_end) else 0.0
		trip["depart_time"] = _fmt_time(trip.depart_time)
		trip["notes"] = trip.notes or trip.checkout_notes

	return trips


def _get_chart(rows):
	"""Billable KM per vehicle - the bar chart a manager checks the invoice against."""
	if not rows:
		return None

	totals = {}
	for row in rows:
		label = row.get("license_plate") or row.get("vehicle") or _("Unknown")
		totals[label] = flt(totals.get(label, 0)) + flt(row.get("billable_km"))

	labels = sorted(totals)
	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Billable KM"), "values": [flt(totals[k], 1) for k in labels]}],
		},
		"type": "bar",
		"colors": ["#E65100"],
	}


def _get_summary(rows):
	billable = sum(flt(r.get("billable_km")) for r in rows)
	cost = sum(flt(r.get("additional_cost")) for r in rows)
	completed = len([r for r in rows if r.get("status") == "completed"])

	return [
		{"label": _("Trips"), "value": len(rows), "datatype": "Int"},
		{"label": _("Completed"), "value": completed, "datatype": "Int"},
		{"label": _("Billable KM"), "value": flt(billable, 1), "datatype": "Float", "indicator": "Green"},
		{"label": _("Additional Cost"), "value": flt(cost, 2), "datatype": "Currency"},
	]
