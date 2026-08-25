// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports['Employee Transfer and Promotion'] = {
	filters: [
		{
			fieldname: 'from_date',
			label: __('From Date'),
			fieldtype: 'Date',
			default: frappe.datetime.year_start(),
			reqd: 1,
		},
		{
			fieldname: 'to_date',
			label: __('To Date'),
			fieldtype: 'Date',
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: 'type',
			label: __('Type'),
			fieldtype: 'Select',
			// Blank = both doctypes.
			options: ['', 'Transfer', 'Promotion'].join('\n'),
		},
		{
			fieldname: 'employee',
			label: __('Employee'),
			fieldtype: 'Link',
			options: 'Employee',
		},
		{
			fieldname: 'status',
			label: __('Status'),
			fieldtype: 'Select',
			// Blank hides Cancelled but keeps Draft, which matters while a backfill
			// import is still sitting unsubmitted.
			options: ['', 'Draft', 'Submitted', 'Cancelled'].join('\n'),
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// A row with no property is a document that changes nothing — the signature of
		// an import that filled the Property label column but left Field Name empty.
		if (column.fieldname === 'property' && data && !data.fieldname) {
			value = `<span style="color: var(--red-500)">${__('no property')}</span>`;
		}

		if (column.fieldname === 'status' && data && data.status === 'Draft') {
			value = `<span style="color: var(--orange-500)">${value}</span>`;
		}

		return value;
	},
};
