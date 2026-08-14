frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Daily Attendance Trend"] = {
	method: "customize_erpnext.customize_erpnext.dashboard_chart_source.daily_attendance_trend.daily_attendance_trend.get_data",
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
