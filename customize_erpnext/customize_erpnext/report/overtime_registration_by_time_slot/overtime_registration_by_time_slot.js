// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Overtime Registration by Time Slot"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.week_start(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.week_end(),
			"reqd": 1
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": ["Draft", "Submitted", "All (except Cancelled)"],
			"default": "Draft"
		},
		{
			"fieldname": "group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group"
		},
		{
			"fieldname": "section",
			"label": __("Section"),
			"fieldtype": "Link",
			"options": "Section"
		}
	]
};
