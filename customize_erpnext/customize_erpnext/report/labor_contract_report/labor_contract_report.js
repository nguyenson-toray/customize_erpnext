// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports['Labor Contract Report'] = {
	filters: [
		{
			fieldname: 'from_next_sign_date',
			label: __('Next Sign Date From'),
			fieldtype: 'Date',
		},
		{
			fieldname: 'to_next_sign_date',
			label: __('Next Sign Date To'),
			fieldtype: 'Date',
		},
		{
			fieldname: 'from_start_date',
			label: __('Start Date From'),
			fieldtype: 'Date',
		},
		{
			fieldname: 'to_start_date',
			label: __('Start Date To'),
			fieldtype: 'Date',
		},
		{
			fieldname: 'status',
			label: __('Status'),
			fieldtype: 'Select',
			options: ['', 'Upcoming', 'Signed', 'Overdue'].join('\n'),
		},
		{
			fieldname: 'contract_type',
			label: __('Contract Type'),
			fieldtype: 'Link',
			options: 'Employment Type',
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
		{
			fieldname: 'employee_status',
			label: __('Employee Status'),
			fieldtype: 'Select',
			options: ['', 'Active', 'Inactive', 'Suspended', 'Left'].join('\n'),
			default: 'Active',
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === 'status' && data) {
			// --{colour}-600 is the readable "coloured text" token in both themes;
			// --text-on-{colour} is for text sitting ON a coloured background.
			const colors = { Signed: 'green', Overdue: 'red', Upcoming: 'orange' };
			const color = colors[data.status];
			if (color) {
				value = `<span style="color: var(--${color}-600); font-weight: 600;">${value}</span>`;
			}
		}
		return value;
	},
};
