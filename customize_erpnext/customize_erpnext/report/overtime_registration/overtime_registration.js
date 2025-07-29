// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Overtime Registration"] = {
	"filters": [
		{
			"fieldname": "request_date",
			"label": __("Request Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": [
				"",
				"Draft",
				"Pending Manager Approval",
				"Pending Factory Manager Approval",
				"Approved",
				"Rejected",
				"Cancelled"
			]
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group"
		},
		{
			"fieldname": "employee",
			"label": __("Employee"),
			"fieldtype": "Link",
			"options": "Employee"
		},
		{
			"fieldname": "employee_name",
			"label": __("Employee Name"),
			"fieldtype": "Data"
		}
	],
	"onload": function (report) {
		// Set default period to current week
		let today = frappe.datetime.get_today();
		let start_of_week = frappe.datetime.add_days(today, -frappe.datetime.get_day_diff(today, frappe.datetime.week_start()));
		let end_of_next_week = frappe.datetime.add_days(start_of_week, 13);

		report.set_filter_value('from_date', start_of_week);
		report.set_filter_value('to_date', end_of_next_week);
	}
};
