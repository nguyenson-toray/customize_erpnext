// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Overtime Registration Quantity"] = {
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
			"default": frappe.datetime.add_days(frappe.datetime.week_end(), 7),
			"reqd": 1
		},
		{
			"fieldname": "group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group"
		}
	],

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
