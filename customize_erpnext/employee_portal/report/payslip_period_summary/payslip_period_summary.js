// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports['Payslip Period Summary'] = {
	filters: [
		{
			fieldname: 'period',
			label: __('Pay Period'),
			fieldtype: 'Select',
			reqd: 1,
			// Periods that have payslips, newest first - filled in onload.
			options: [],
		},
		{
			fieldname: 'status',
			label: __('Status'),
			fieldtype: 'Select',
			options: ['', 'Draft', 'Published', 'Withdrawn'].join('\n'),
		},
		{
			fieldname: 'viewed',
			label: __('Viewed'),
			fieldtype: 'Select',
			options: ['', 'Viewed', 'Not Viewed'].join('\n'),
		},
		{
			fieldname: 'final_settlement',
			label: __('Final Settlement'),
			fieldtype: 'Select',
			options: ['', 'Yes', 'No'].join('\n'),
		},
	],
	onload(report) {
		frappe
			.call({ method: 'customize_erpnext.employee_portal.payslip_admin.get_report_periods', type: 'GET' })
			.then((r) => {
				const m = r.message || {};
				const filter = report.get_filter('period');
				filter.df.options = (m.periods || []).map((p) => ({ value: p.value, label: p.label }));
				filter.refresh();
				if (m.default) report.set_filter_value('period', m.default);
			});
	},
};
