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
			"default": frappe.datetime.add_days(frappe.datetime.week_end(), 7),
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
	],

	onload: function (report) {
		// Hide the Status filter while Overtime Registration is not submittable
		frappe.model.with_doctype("Overtime Registration", () => {
			if (frappe.get_meta("Overtime Registration").is_submittable) return;
			const status_filter = report.get_filter("status");
			if (status_filter) status_filter.toggle(false);
		});
	}
};
