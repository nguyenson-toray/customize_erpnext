# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "request_date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 110
		},
		{
			"fieldname": "vehicle_name",
			"label": _("Vehicle"),
			"fieldtype": "Link",
			"options": "Vehicle List",
			"width": 100
		},		
		{
			"fieldname": "trip_type",
			"label": _("Type"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "start_location",
			"label": _("From"),
			"fieldtype": "Data",
			"width": 170
		},
		{
			"fieldname": "destination_location",
			"label": _("To"),
			"fieldtype": "Data",
			"width": 170
		},
		{
			"fieldname": "start_time",
			"label": _("Start Time"),
			"fieldtype": "Datetime",
			"width": 170
		},
		{
			"fieldname": "finish_time",
			"label": _("Finish Time"),
			"fieldtype": "Datetime",
			"width": 170
		},
		{
			"fieldname": "start_km",
			"label": _("Start Km"),
			"fieldtype": "Int",
			"width": 80
		},
		{
			"fieldname": "finish_km",
			"label": _("Finish Km"),
			"fieldtype": "Int",
			"width": 80
		},
		{
			"fieldname": "total_km",
			"label": _("Total Km"),
			"fieldtype": "Int",
			"width": 80
		},
		{
			"fieldname": "other_fees",
			"label": _("Other Fees"),
			"fieldtype": "Currency",
			"width": 100
		},
		{
			"fieldname": "name",
			"label": _("Trip ID"),
			"fieldtype": "Link",
			"options": "Vehicle Trip",
			"width": 180
		}
	]


def get_data(filters):
	conditions = get_conditions(filters)

	data = frappe.db.sql("""
		SELECT
			request_date,
			vehicle_name,
			CASE
				WHEN daily_pickup = 1 THEN 'Daily Pickup'
				WHEN daily_dropoff = 1 THEN 'Daily Dropoff'
				ELSE 'Other'
			END as trip_type,
			start_location,
			destination_location,
			start_time,
			finish_time,
			start_km,
			finish_km,
			total_km,
			other_fees,
			name
		FROM
			`tabVehicle Trip`
		WHERE
			status = 'Hoàn Thành'
			AND {conditions}
		ORDER BY
			request_date DESC, vehicle_name, start_time
	""".format(conditions=conditions), filters, as_dict=1)

	return data


def get_conditions(filters):
	conditions = []

	if filters.get("from_date"):
		conditions.append("request_date >= %(from_date)s")

	if filters.get("to_date"):
		conditions.append("request_date <= %(to_date)s")

	if filters.get("vehicle_name"):
		conditions.append("vehicle_name = %(vehicle_name)s")

	return " AND ".join(conditions) if conditions else "1=1"
