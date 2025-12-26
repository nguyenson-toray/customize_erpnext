// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Shift Attendance Customize"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: function() {
				// Default to 26th of previous month
				let date = frappe.datetime.get_today();
				let current_day = frappe.datetime.str_to_obj(date).getDate();

				// If current day is before 26th, go back to 26th of month before last
				if (current_day < 26) {
					date = frappe.datetime.add_months(date, -2);
				} else {
					date = frappe.datetime.add_months(date, -1);
				}

				// Set to 26th
				let year = frappe.datetime.str_to_obj(date).getFullYear();
				let month = frappe.datetime.str_to_obj(date).getMonth();
				return frappe.datetime.obj_to_str(new Date(year, month, 26));
			}(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "shift",
			label: __("Shift Type"),
			fieldtype: "Link",
			options: "Shift Type",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Present", "Absent", "Maternity Leave", "On Leave", "Half Day", "Work From Home"],
		},
		{
			fieldname: "group",
			label: __("Group"),
			fieldtype: "Link",
			options: "Group",
			get_query: function() {
				return {
					filters: {
						"docstatus": ["!=", 2]
					}
				};
			}
		},
		{
			fieldname: "late_entry",
			label: __("Late Entry"),
			fieldtype: "Check",
		},
		{
			fieldname: "early_exit",
			label: __("Early Exit"),
			fieldtype: "Check",
		},
		{
			fieldname: "detail_join_resign_date",
			label: __("Detail Join / Resign Date"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "summary",
			label: __("Summary"),
			fieldtype: "Check",
			default: 0,
			on_change: function() {
				// When Summary is checked, auto-check Detail Join / Resign Date
				if (frappe.query_report.get_filter_value('summary')) {
					frappe.query_report.set_filter_value('detail_join_resign_date', 1);
				}
				// Refresh report when Summary changes
				frappe.query_report.refresh();
			}
		},
	],
	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);
		if (
			(column.fieldname === "in_time" && data.late_entry) ||
			(column.fieldname === "out_time" && data.early_exit)
		) {
			value = `<span style='color:red!important'>${value}</span>`;
		}
		return value;
	},
};
