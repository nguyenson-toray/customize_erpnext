// Uniform Tracking — filters + status colours.
frappe.query_reports['Uniform Tracking'] = {
	filters: [
		{
			fieldname: 'status',
			label: __('Status'),
			fieldtype: 'Select',
			options: ['', 'Not Issued', 'Active', 'Due Soon', 'Overdue'].join('\n'),
		},
		{ fieldname: 'employee', label: __('Employee'), fieldtype: 'Link', options: 'Employee' },
		{ fieldname: 'department', label: __('Department'), fieldtype: 'Link', options: 'Department' },
		{ fieldname: 'section', label: __('Section'), fieldtype: 'Link', options: 'Section' },
		{ fieldname: 'group', label: __('Group'), fieldtype: 'Link', options: 'Group' },
		{
			fieldname: 'uniform_type',
			label: __('Uniform Type'),
			fieldtype: 'Link',
			options: 'Item',
			get_query: () => ({ filters: { has_variants: 1 } }),
		},
		{ fieldname: 'due_from', label: __('Due Date From'), fieldtype: 'Date' },
		{ fieldname: 'due_to', label: __('Due Date To'), fieldtype: 'Date' },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === 'status' && data) {
			const color = { Overdue: 'red', 'Due Soon': 'orange', Active: 'green', 'Not Issued': 'gray' }[
				data.status
			];
			if (color) value = `<span class="indicator-pill ${color}">${__(data.status)}</span>`;
		}
		return value;
	},
};
