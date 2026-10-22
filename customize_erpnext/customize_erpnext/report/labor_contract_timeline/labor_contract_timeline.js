// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports['Labor Contract Timeline'] = {
	filters: [
		{
			fieldname: 'active_only',
			label: __('Active Employees Only'),
			fieldtype: 'Check',
			default: 1,
		},
		{
			fieldname: 'needs_signing',
			label: __('Needs Signing'),
			fieldtype: 'Check',
			description: __('Only employees with an unsigned contract or appendix, soonest first'),
		},
		{
			fieldname: 'sort_by_next_sign_date',
			label: __('Sort by Next Sign Date'),
			fieldtype: 'Check',
		},
		{
			fieldname: 'employee',
			label: __('Employee'),
			fieldtype: 'Link',
			options: 'Employee',
		},
		{
			fieldname: 'custom_section',
			label: __('Section'),
			fieldtype: 'Link',
			options: 'Section',
		},
		{
			fieldname: 'custom_group',
			label: __('Group'),
			fieldtype: 'Link',
			options: 'Group',
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) {
			return value;
		}
		// --{colour}-600 is the readable "coloured text" token in both themes
		if (column.fieldname.endsWith('_status')) {
			const colors = { Signed: 'green', Overdue: 'red', Upcoming: 'orange' };
			const color = colors[data[column.fieldname]];
			if (color) {
				value = `<span style="color: var(--${color}-600); font-weight: 600;">${value}</span>`;
			}
		}
		if (column.fieldname === 'days_left' && data.days_left !== null && data.days_left !== undefined) {
			const color = data.days_left < 0 ? 'red' : data.days_left <= 30 ? 'orange' : null;
			if (color) {
				value = `<span style="color: var(--${color}-600); font-weight: 600;">${value}</span>`;
			}
		}
		return value;
	},
};
