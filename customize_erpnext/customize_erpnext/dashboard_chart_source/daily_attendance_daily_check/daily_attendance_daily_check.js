frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Daily Attendance Daily Check"] = {
	method: "customize_erpnext.customize_erpnext.dashboard_chart_source.daily_attendance_daily_check.daily_attendance_daily_check.get_data",
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
