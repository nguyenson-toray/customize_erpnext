// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Overtime Registration Quantity"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group"
		}
	],
	"onload": function (report) {
		// Set default period to current week
		let today = frappe.datetime.get_today();
		let start_of_week = frappe.datetime.add_days(today, -frappe.datetime.get_day_diff(today, frappe.datetime.week_start()));
		let end_of_next_week = frappe.datetime.add_days(start_of_week, 13);

		report.set_filter_value('from_date', start_of_week);
		report.set_filter_value('to_date', end_of_next_week);
	},
	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "total_employees_submitted" || column.fieldname === "total_hours_submitted") {
			// Green color for submitted data
			value = `<span style="color: green; font-weight: normal;">${value}</span>`;
		}
		else
			if (column.fieldname === "total_employees_draft" || column.fieldname === "total_hours_draft") {
				// Gray color and italic for draft data
				value = `<span style="color: gray; font-style: italic;">${value}</span>`;
			}

		return value;
	}
};
