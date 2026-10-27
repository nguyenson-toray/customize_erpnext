// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// TIQN Payslip list: status colours + "Download PDF". Importing, publishing and
// withdrawing are on the Payslip Upload page only (27/10/2026: list buttons removed).

frappe.listview_settings['TIQN Payslip'] = {
	add_fields: ['status', 'period', 'net_pay'],
	get_indicator(doc) {
		const color = { Draft: 'orange', Published: 'green', Withdrawn: 'gray' }[doc.status] || 'gray';
		return [__(doc.status, null, 'Payslip'), color, `status,=,${doc.status}`];
	},
	onload(listview) {
		if (!frappe.user.has_role(['CnB', 'System Manager'])) return;
		// A4 PDFs of the ticked payslips or of a whole period (~1,000): built in the background.
		listview.page.add_inner_button(__('Download PDF'), () => payslip_pdf_dialog(listview));
	},
};

// "Download PDF": the ticked payslips (default when any are ticked) or by filters - a
// period and / or employees (no period = every period of theirs) or Sections or one Group
// (one of the three), optionally a status - as a ZIP of one PDF each (default) or one combined PDF to print in one
// go. One payslip = its PDF.
// Server: payslip_print.start_pdf_job -> background job -> poll -> download once.
function payslip_pdf_dialog(listview) {
	const api = 'customize_erpnext.employee_portal.payslip_print';
	const ticked = listview.get_checked_items(true);
	frappe.call({ method: `${api}.pdf_job_options`, type: 'GET' }).then((r) => {
		const m = r.message || {};
		const listed = (listview.filters || []).find((f) => f[1] === 'period' && f[2] === '=');
		const by_period = 'eval:doc.source === "period"';
		// `d` is assigned below; onchange / get_data may run while the dialog is being built.
		let d = null;
		// Employees, Sections and Group: one of the three only - picking one clears the others.
		const has = (v) => (Array.isArray(v) ? v.length > 0 : !!v);
		const only = (keep) => {
			if (!d || !has(d.get_value(keep))) return;
			for (const f of ['employees', 'sections', 'group']) {
				if (f !== keep && has(d.get_value(f))) d.set_value(f, f === 'group' ? '' : []);
			}
		};
		d = new frappe.ui.Dialog({
			title: __('Download PDF'),
			fields: [
				{
					fieldtype: 'Select',
					fieldname: 'source',
					label: __('Payslips'),
					options: [
						{ value: 'ticked', label: __('Ticked payslips ({0})', [ticked.length]) },
						{ value: 'period', label: __('By pay period / employee') },
					],
					default: ticked.length ? 'ticked' : 'period',
					hidden: !ticked.length,
				},
				{
					fieldtype: 'Select',
					fieldname: 'period',
					label: __('Pay Period'),
					options: [''].concat(m.periods || []),
					default: (listed && listed[3]) || (m.periods || [])[0],
					depends_on: by_period,
					description: __('Empty = every period of the employees below.'),
				},
				{
					fieldtype: 'MultiSelectList',
					fieldname: 'employees',
					label: __('Employees'),
					options: 'Employee',
					depends_on: by_period,
					// Not Exclude Employees (Attendance Calculation Setting), not those who left
					// before the period.
					get_data: (txt) =>
						frappe
							.call({ method: `${api}.search_pdf_employees`, args: { txt, period: d.get_value('period') }, type: 'GET' })
							.then((r) => r.message || []),
					onchange: () => only('employees'),
					description: __('Employees, Sections or Group: pick one of the three (empty = everyone).'),
				},
				{
					fieldtype: 'MultiSelectList',
					fieldname: 'sections',
					label: __('Sections'),
					options: 'Section',
					depends_on: by_period,
					get_data: (txt) => frappe.db.get_link_options('Section', txt),
					onchange: () => only('sections'),
				},
				{
					fieldtype: 'Link',
					fieldname: 'group',
					label: __('Group'),
					options: 'Group',
					depends_on: by_period,
					onchange: () => only('group'),
				},
				{
					fieldtype: 'Select',
					fieldname: 'status',
					label: __('Status'),
					options: [
						{ value: 'Published', label: __('Published', null, 'Payslip') },
						{ value: '', label: __('All') },
						{ value: 'Draft', label: __('Draft', null, 'Payslip') },
						{ value: 'Withdrawn', label: __('Withdrawn', null, 'Payslip') },
					],
					default: 'Published',
					depends_on: by_period,
					description: __('Draft / Withdrawn payslips print with a DRAFT watermark.'),
				},
				{
					fieldtype: 'Select',
					fieldname: 'mode',
					label: __('Output'),
					options: [
						{ value: 'zip', label: __('ZIP - one PDF per payslip') },
						{ value: 'combined', label: __('One combined PDF') },
					],
					default: 'zip',
					description: __('One combined PDF prints the whole selection in one go.'),
				},
			],
			primary_action_label: __('Download'),
			primary_action: (v) => {
				const employees = v.employees || [];
				if (v.source !== 'ticked' && !v.period && !employees.length) {
					frappe.msgprint(__('Pick a pay period or employees.'));
					return;
				}
				const args =
					v.source === 'ticked'
						? { names: JSON.stringify(ticked), mode: v.mode }
						: {
								period: v.period,
								employees: JSON.stringify(employees),
								sections: JSON.stringify(v.sections || []),
								group: v.group,
								status: v.status,
								mode: v.mode,
						  };
				frappe.call({ method: `${api}.start_pdf_job`, args, freeze: true }).then((res) => {
					d.hide();
					wait_pdf_job(api, res.message.token, res.message.total);
				});
			},
		});
		d.show();
	});
}

function wait_pdf_job(api, token, total) {
	const title = __('Preparing PDF');
	frappe.show_progress(title, 0, total, __('Queued...'));
	const poll = () =>
		frappe
			.call({ method: `${api}.pdf_job_status`, args: { token }, type: 'GET' })
			.then((r) => {
				const s = r.message || {};
				if (s.status === 'done') {
					frappe.hide_progress();
					open_url_post(frappe.request.url, { cmd: `${api}.download_pdf_job`, token });
				} else if (s.status === 'error') {
					frappe.hide_progress();
					frappe.msgprint({ message: __('Could not build the PDF - see Error Log.'), indicator: 'red' });
				} else {
					frappe.show_progress(title, s.done || 0, s.total || total, __('{0} / {1} payslips', [s.done || 0, s.total || total]));
					setTimeout(poll, 2000);
				}
			})
			.catch(() => frappe.hide_progress());
	setTimeout(poll, 2000);
}
