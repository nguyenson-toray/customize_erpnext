// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Vehicle Trip Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_start(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_end(),
			"reqd": 1
		},
		{
			"fieldname": "vehicle_name",
			"label": __("Vehicle"),
			"fieldtype": "Link",
			"options": "Vehicle List"
		},
		{
			"fieldname": "only_show_finished_trip",
			"label": __("Only Show Finished Trip"),
			"fieldtype": "Check",
			"default": 1
		}
	]
};
