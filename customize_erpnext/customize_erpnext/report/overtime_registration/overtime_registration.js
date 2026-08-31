// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Overtime Registration"] = {
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
			"fieldname": "employee",
			"label": __("Employee"),
			"fieldtype": "Link",
			"options": "Employee"
		},
		{
			"fieldname": "group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"default": "",
			"options": [
				"",
				"Draft",
				"Submitted",
				"Cancelled"
			]
		}
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "status") {
			if (value === "Submitted") {
				// Green color for submitted status
				value = `<span style="color: green;">${value}</span>`;
			}
			else if (value === "Draft") {
				// Orange color and italic for draft status
				value = `<span style="color: orange; font-style: italic;">${value}</span>`;
			}
		}

		return value;
	}
};
