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

// "Download PDF": the ticked payslips (default when any are ticked) or every payslip of a
// period (optionally one Section / Group / status), as a ZIP of one PDF each (default) or
// one combined PDF to print in one go. One payslip = its PDF.
// Server: payslip_print.start_pdf_job -> background job -> poll -> download once.
function payslip_pdf_dialog(listview) {
	const api = 'customize_erpnext.employee_portal.payslip_print';
	const ticked = listview.get_checked_items(true);
	frappe.call({ method: `${api}.pdf_job_options`, type: 'GET' }).then((r) => {
		const m = r.message || {};
		const listed = (listview.filters || []).find((f) => f[1] === 'period' && f[2] === '=');
		const by_period = 'eval:doc.source === "period"';
		// `d` is assigned below; onchange / get_query may run while the dialog is being built.
		let d = null;
		d = new frappe.ui.Dialog({
			title: __('Download PDF'),
			fields: [
				{
					fieldtype: 'Select',
					fieldname: 'source',
					label: __('Payslips'),
					options: [
						{ value: 'ticked', label: __('Ticked payslips ({0})', [ticked.length]) },
						{ value: 'period', label: __('By pay period') },
					],
					default: ticked.length ? 'ticked' : 'period',
					hidden: !ticked.length,
				},
				{
					fieldtype: 'Select',
					fieldname: 'period',
					label: __('Pay Period'),
					options: m.periods || [],
					default: (listed && listed[3]) || (m.periods || [])[0],
					depends_on: by_period,
					mandatory_depends_on: by_period,
				},
				{
					fieldtype: 'Link',
					fieldname: 'section',
					label: __('Section'),
					options: 'Section',
					depends_on: by_period,
					onchange: () => d && d.set_value('group', ''),
				},
				{
					fieldtype: 'Link',
					fieldname: 'group',
					label: __('Group'),
					options: 'Group',
					depends_on: by_period,
					// Groups of the picked Section only (Group.parrent -> Section).
					get_query: () => (d && d.get_value('section') ? { filters: { parrent: d.get_value('section') } } : {}),
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
				const args =
					v.source === 'ticked'
						? { names: JSON.stringify(ticked), mode: v.mode }
						: { period: v.period, section: v.section, group: v.group, status: v.status, mode: v.mode };
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
