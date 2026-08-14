frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Daily Attendance Sewing Lines"] = {
	method: "customize_erpnext.customize_erpnext.dashboard_chart_source.daily_attendance_sewing_lines.daily_attendance_sewing_lines.get_data",
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
