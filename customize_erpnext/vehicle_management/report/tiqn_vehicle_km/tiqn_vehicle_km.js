// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// Frappe hard-codes the report chart to 280px in get_chart_options()
// (query_report.js:1205), overwriting anything execute() returns - so the height
// has to be corrected after the chart is drawn. CSS cannot do it either:
// frappe-charts writes width/height ATTRIBUTES on the <svg> with no viewBox, so a
// CSS height clips the drawing instead of scaling it.
const CHART_HEIGHT = 180;

frappe.query_reports['TIQN Vehicle KM'] = {
	after_refresh(report) {
		// Frappe rebuilds chart_options on every refresh, resetting the height, so
		// this runs each time rather than once. render_chart() does not fire
		// after_refresh, so there is no loop.
		if (!report.chart_options || report.chart_options.height === CHART_HEIGHT) return;
		report.chart_options.height = CHART_HEIGHT;
		report.render_chart(report.chart_options);
	},

	filters: [
		{
			fieldname: 'from_date',
			label: __('From Date'),
			fieldtype: 'Date',
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: 'to_date',
			label: __('To Date'),
			fieldtype: 'Date',
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: 'vehicle',
			label: __('Vehicle'),
			fieldtype: 'Link',
			options: 'TIQN Vehicle',
		},
		{
			fieldname: 'driver',
			label: __('Driver'),
			fieldtype: 'Link',
			options: 'TIQN Driver',
		},
		{
			fieldname: 'status',
			label: __('Status'),
			fieldtype: 'Select',
			// Completed only by default: those are the trips TIQN actually pays for.
			options: ['', 'completed', 'in_progress', 'scheduled', 'confirmed', 'cancelled'].join('\n'),
			default: 'completed',
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === 'billable_km' && data && flt(data.billable_km)) {
			value = `<b>${value}</b>`;
		}
		if (column.fieldname === 'status' && data) {
			const colour = {
				completed: 'green',
				in_progress: 'orange',
				scheduled: 'blue',
				confirmed: 'blue',
				cancelled: 'red',
			}[data.status];
			if (colour) value = `<span class="indicator-pill ${colour}">${data.status}</span>`;
		}
		return value;
	},
};
