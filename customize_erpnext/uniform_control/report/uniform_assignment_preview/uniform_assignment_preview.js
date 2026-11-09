// Uniform Assignment Preview — what each employee gets under the current rules.
frappe.query_reports['Uniform Assignment Preview'] = {
	filters: [
		{ fieldname: 'department', label: __('Department'), fieldtype: 'Link', options: 'Department' },
		{ fieldname: 'section', label: __('Section'), fieldtype: 'Link', options: 'Section' },
		{ fieldname: 'group', label: __('Group'), fieldtype: 'Link', options: 'Group' },
		{ fieldname: 'only_problems', label: __('Only Problems'), fieldtype: 'Check' },
		{ fieldname: 'manual_only', label: __('Only Manual Override'), fieldtype: 'Check' },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === 'problems' && data && data.problems) {
			value = `<span style="color:var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
