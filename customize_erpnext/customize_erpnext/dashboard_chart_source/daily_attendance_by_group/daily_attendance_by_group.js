frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Daily Attendance by Group"] = {
	method: "customize_erpnext.customize_erpnext.dashboard_chart_source.daily_attendance_by_group.daily_attendance_by_group.get_data",
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
