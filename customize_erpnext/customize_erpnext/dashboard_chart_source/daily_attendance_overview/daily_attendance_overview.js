frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Daily Attendance Overview"] = {
	method: "customize_erpnext.customize_erpnext.dashboard_chart_source.daily_attendance_overview.daily_attendance_overview.get_data",
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
