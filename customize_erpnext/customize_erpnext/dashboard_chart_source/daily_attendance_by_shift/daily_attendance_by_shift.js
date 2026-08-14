frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Daily Attendance by Shift"] = {
	method: "customize_erpnext.customize_erpnext.dashboard_chart_source.daily_attendance_by_shift.daily_attendance_by_shift.get_data",
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
