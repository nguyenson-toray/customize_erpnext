// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

const LC_EXPORT_ROLES = ['HR Manager', 'HR User', 'System Manager'];

frappe.query_reports['Labor Contract Report'] = {
	filters: [
		{
			fieldname: 'current_only',
			label: __('Current Contract Only'),
			fieldtype: 'Check',
			default: 1,
			description: __('Only the contract in force today, for employees still working — one row per employee. Untick to see the full history.'),
		},
		{
			fieldname: 'expiring',
			label: __('Expiring'),
			fieldtype: 'Select',
			options: [
				{ value: '', label: '' },
				{ value: 'This Week', label: __('This Week') },
				{ value: 'Next Week', label: __('Next Week') },
				{ value: 'This Month', label: __('This Month') },
				{ value: 'Next Month', label: __('Next Month') },
				{ value: 'Next 30 Days', label: __('Next 30 Days') },
				{ value: 'Next 60 Days', label: __('Next 60 Days') },
				{ value: 'Custom', label: __('Custom') },
			],
			description: __('By contract End Date'),
		},
		{
			fieldname: 'from_date',
			label: __('End Date From'),
			fieldtype: 'Date',
			depends_on: "eval:doc.expiring == 'Custom'",
		},
		{
			fieldname: 'to_date',
			label: __('End Date To'),
			fieldtype: 'Date',
			depends_on: "eval:doc.expiring == 'Custom'",
		},
		{
			fieldname: 'overdue_30',
			label: __('Overdue > 30 Days'),
			fieldtype: 'Check',
			description: __('Not signed more than 30 days after it should have taken effect — including an expired contract whose follow-up was never created. A fixed-term contract left unsigned this long after the previous one expired becomes indefinite-term (Labor Code 2019, Art. 20.2).'),
		},
		{
			fieldname: 'document_type',
			label: __('Document Type'),
			fieldtype: 'Select',
			options: [
				{ value: '', label: '' },
				{ value: 'Contract', label: __('Contract') },
				{ value: 'Appendix', label: __('Appendix') },
			],
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
		// {
		// 	fieldname: 'custom_section',
		// 	label: __('Section'),
		// 	fieldtype: 'Link',
		// 	options: 'Section',
		// },
		// {
		// 	fieldname: 'custom_group',
		// 	label: __('Group'),
		// 	fieldtype: 'Link',
		// 	options: 'Group',
		// },
	],

	onload: function (report) {
		// Personal data (ID card, address, bank, salary) — HR only, re-checked server-side
		if (!frappe.user.has_role(LC_EXPORT_ROLES)) {
			return;
		}
		report.page.add_inner_button(__('Export Contract Data'), function () {
			// open_url_post = form POST → the browser downloads the file directly
			open_url_post(
				'/api/method/customize_erpnext.customize_erpnext.report.labor_contract_report.labor_contract_report.export_contract_data',
				{ filters: JSON.stringify(report.get_filter_values()) }
			);
		});
	},

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) {
			return value;
		}

		// --{colour}-600 is the readable "coloured text" token in both themes;
		// --text-on-{colour} is for text sitting ON a coloured background.
		if (column.fieldname === 'days_left' && data.days_left !== null && data.days_left !== undefined) {
			const color =
				data.days_left < 0 ? 'red' : data.days_left <= (data.warning_before || 0) ? 'orange' : null;
			if (color) {
				value = `<span style="color: var(--${color}-600); font-weight: 600;">${value}</span>`;
			}
		}

		if (column.fieldname === 'days_overdue' && data.days_overdue) {
			const late = data.days_overdue > 30;
			const title = data.legal_risk
				? __('Unsigned for over 30 days after the previous fixed-term contract expired — by law it may already count as an indefinite-term contract (Labor Code 2019, Art. 20.2).')
				: late
					? __('Unsigned for over 30 days')
					: '';
			value = `<span style="color: var(--${late ? 'red' : 'orange'}-600); font-weight: 600;" title="${title}">${late ? '⚠ ' : ''}${value}</span>`;
		}

		// Leaving on/before the next sign date: no renewal, so mute the "next" columns
		if (column.fieldname === 'next_contract_status' && data.next_contract_status) {
			const colors = { Signed: 'green', Overdue: 'red', Upcoming: 'orange', 'Not Created': 'gray' };
			value = `<span style="color: var(--${colors[data.next_contract_status] || 'gray'}-600); font-weight: 600;">${__(data.next_contract_status)}</span>`;
		}

		if (data.leaves_before_next && ['next_sign_date', 'next_contract_type'].includes(column.fieldname)) {
			const title = __('Leaves on {0} — no next contract', [
				frappe.datetime.str_to_user(data.relieving_date),
			]);
			value = `<span class="text-muted" style="text-decoration: line-through;" title="${title}">${value}</span>`;
		}

		if (column.fieldname === 'status') {
			const colors = { Signed: 'green', Overdue: 'red', Upcoming: 'orange' };
			const color = colors[data.status];
			if (color) {
				value = `<span style="color: var(--${color}-600); font-weight: 600;">${value}</span>`;
			}
		}
		return value;
	},
};
