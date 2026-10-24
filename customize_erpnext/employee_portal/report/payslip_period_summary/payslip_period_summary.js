// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports['Payslip Period Summary'] = {
	filters: [
		{
			fieldname: 'period',
			label: __('Pay Period'),
			fieldtype: 'Data',
			reqd: 1,
			description: __('YYYY-MM, e.g. 2026-09'),
			default: (() => {
				// The last period that has ENDED (periods run from the 26th to the 25th).
				const d = new Date();
				const month = d.getDate() > 25 ? d.getMonth() : d.getMonth() - 1;
				const p = new Date(d.getFullYear(), month, 1);
				return `${p.getFullYear()}-${String(p.getMonth() + 1).padStart(2, '0')}`;
			})(),
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
};
