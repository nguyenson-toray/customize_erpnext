// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// "Import from Excel" on the TIQN Payslip list: one Excel row per employee, components
// as columns - the child table makes Frappe's Data Import unusable for HR. Same server
// checks as the Payslip Upload page (employee_portal.payslip_admin): preview -> errors /
// warnings -> import as Draft. Publishing stays on the Payslip Upload page.

const PS_API = 'customize_erpnext.employee_portal.payslip_admin';
let ps_import_done = null;

frappe.listview_settings['TIQN Payslip'] = {
	add_fields: ['status', 'period', 'net_pay'],
	get_indicator(doc) {
		const color = { Draft: 'orange', Published: 'green', Withdrawn: 'gray' }[doc.status] || 'gray';
		return [__(doc.status, null, 'Payslip'), color, `status,=,${doc.status}`];
	},
	onload(listview) {
		if (!frappe.user.has_role(['CnB', 'System Manager'])) return;
		listview.page.add_inner_button(__('Import from Excel'), () => new PayslipImportDialog(listview));
		listview.page.add_inner_button(__('Publish / Withdraw'), () => frappe.set_route('payslip-upload'));
		// Named handler: off() without one would also drop the Payslip Upload page's listener.
		if (ps_import_done) frappe.realtime.off('payslip_import_done', ps_import_done);
		ps_import_done = (data) => {
			frappe.show_alert({
				message: __('Imported {0} payslips as Draft (batch {1})', [data.rows, data.batch]),
				indicator: 'green',
			});
			listview.refresh();
		};
		frappe.realtime.on('payslip_import_done', ps_import_done);
	},
};

class PayslipImportDialog {
	constructor(listview) {
		this.listview = listview;
		this.file_url = null;
		this.imported = false;
		this.dialog = new frappe.ui.Dialog({
			title: __('Import Payslips from Excel'),
			size: 'extra-large',
			fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
			primary_action_label: __('Import as Draft'),
			primary_action: () => this.do_import(),
			secondary_action_label: __('Close'),
			secondary_action: () => this.dialog.hide(),
			on_hide: () => this.discard(),
		});
		this.$body = this.dialog.fields_dict.body.$wrapper;
		this.$body.html(`
			<div class="text-muted small" style="margin-bottom: 12px">
				${__('One row per employee: No., Period (YYYY-MM or MM-YYYY), Period From, Period To, Pay Date, Employee, Employee Name, Designation, Department, Section, Group, then one column per Salary Component, matched by the code at the start of the header (e.g. "3.2 ..."). No. and Designation are not imported. Period From / To may be inside the period (joined or left during it); empty Pay Date = the monthly pay day.')}
			</div>
			<div style="display: flex; gap: 8px">
				<button class="btn btn-default btn-sm ps-template">${__('Download Template')}</button>
				<button class="btn btn-primary btn-sm ps-upload">${__('Upload Excel')}</button>
			</div>
			<div class="ps-preview" style="margin-top: 16px"></div>
		`);
		this.$body.find('.ps-template').on('click', () => payslip_template_dialog(PS_API));
		this.$body.find('.ps-upload').on('click', () => this.upload());
		this.set_can_import(false);
		this.dialog.show();
	}

	set_can_import(enabled) {
		this.dialog.get_primary_btn().prop('disabled', !enabled);
	}

	upload() {
		this.discard();
		new frappe.ui.FileUploader({
			allow_multiple: false,
			restrictions: { allowed_file_types: ['.xlsx'] },
			make_attachments_public: false,
			allow_toggle_private: false,
			disable_file_browser: true,
			allow_web_link: false,
			allow_take_photo: false,
			on_success: (file_doc) => this.preview(file_doc.file_url),
		});
	}

	preview(file_url) {
		this.file_url = file_url;
		const $p = this.$body.find('.ps-preview').html(`<div class="text-muted">${__('Checking...')}</div>`);
		frappe
			.call({ method: `${PS_API}.preview_upload`, args: { file_url }, freeze: true })
			.then((r) => this.render(r.message))
			.catch(() => $p.empty());
	}

	render(data) {
		this.data = data;
		const esc = frappe.utils.escape_html;
		const rows = data.rows || [];
		const issue_rows = rows.filter((r) => r.errors.length).concat(rows.filter((r) => !r.errors.length && r.warnings.length));

		let html = `<div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center">
			<span class="indicator-pill blue">${__('{0} rows', [rows.length])}</span>
			<span class="indicator-pill ${data.error_count ? 'red' : 'green'}">${__('{0} errors', [data.error_count])}</span>
			<span class="indicator-pill ${data.warning_count ? 'orange' : 'green'}">${__('{0} warnings', [data.warning_count])}</span>
			<span class="text-muted">${__('Periods')}: ${(data.periods || []).map(esc).join(', ') || '-'}</span>
			${data.check_formulas ? '' : `<span class="indicator-pill gray">${__('Formula check off (Settings)')}</span>`}
		</div>`;
		if (data.header_errors.length) {
			html += `<div class="text-danger" style="margin-top: 12px"><b>${__('File layout')}</b><ul>${data.header_errors
				.map((e) => `<li>${esc(e)}</li>`)
				.join('')}</ul></div>`;
		}
		if ((data.missing_components || []).length) {
			html += `<div class="text-warning" style="margin-top: 12px">${__('Not in the file (will be empty)')}: ${data.missing_components
				.map(esc)
				.join(', ')}</div>`;
		}
		if (issue_rows.length) {
			html += `<table class="table table-bordered table-sm" style="margin-top: 12px"><thead><tr>
				<th>${__('Row')}</th><th>${__('Employee')}</th><th>${__('Period')}</th><th>${__('Issues')}</th>
			</tr></thead><tbody>`;
			for (const r of issue_rows) {
				const items = r.errors
					.map((e) => `<li class="text-danger">${esc(e)}</li>`)
					.concat(r.warnings.map((w) => `<li class="text-warning">${esc(w)}</li>`))
					.join('');
				html += `<tr><td>${r.row}</td><td>${esc(r.employee || r.employee_raw)}<div class="text-muted small">${esc(
					r.employee_name || ''
				)}</div></td><td>${esc(r.period || '')}</td><td><ul style="margin: 0; padding-left: 16px">${items}</ul></td></tr>`;
			}
			html += '</tbody></table>';
		}
		if (data.error_count) {
			html += `<div class="text-danger" style="margin-top: 12px">${__('Fix the errors in Excel and upload again.')}</div>`;
		} else if (data.warning_count) {
			html += `<label style="margin-top: 12px; display: flex; gap: 6px; align-items: center; font-weight: normal">
				<input type="checkbox" class="ps-confirm"> ${__('I have checked the warnings above')}</label>`;
		}
		const $p = this.$body.find('.ps-preview').html(html);
		this.set_can_import(!data.error_count && !data.warning_count && rows.length > 0);
		$p.find('.ps-confirm').on('change', (e) => this.set_can_import(e.target.checked));
	}

	do_import() {
		if (!this.file_url || !this.data) return;
		frappe
			.call({
				method: `${PS_API}.import_upload`,
				args: { file_url: this.file_url, confirm_warnings: this.data.warning_count ? 1 : 0 },
				freeze: true,
				freeze_message: __('Importing...'),
			})
			.then((r) => {
				const m = r.message || {};
				// The server deletes the uploaded workbook after importing.
				this.file_url = null;
				this.dialog.hide();
				if (m.queued) {
					frappe.show_alert({
						message: __('{0} rows are being imported in the background. This page refreshes when done.', [m.rows]),
						indicator: 'blue',
					});
				} else {
					frappe.show_alert({ message: __('Imported {0} payslips as Draft', [m.rows]), indicator: 'green' });
					this.listview.refresh();
				}
			});
	}

	discard() {
		// The workbook holds the salaries of a whole period: never leave it in File.
		if (this.file_url) {
			frappe.call({ method: `${PS_API}.discard_upload`, args: { file_url: this.file_url } });
			this.file_url = null;
		}
		this.data = null;
	}
}

// "Download Template": monthly (pick the pay period) or resigned employees (pick the
// relieving date range) - employee columns pre-filled, HR types the numbers.
// Same dialog in tiqn_payslip_list.js and payslip_upload.js (no shared bundle for the two).
function payslip_template_dialog(api) {
	frappe.call({ method: `${api}.get_template_periods`, type: 'GET' }).then((r) => {
		const m = r.message || {};
		const d = new frappe.ui.Dialog({
			title: __('Download Template'),
			fields: [
				{
					fieldtype: 'Check',
					fieldname: 'resigned',
					label: __('Resigned Employees Only'),
					description: __(
						'Employees who left in the date range below, paid separately within 14 days of leaving. Period To = the day before the relieving date; Pay Date is filled in.'
					),
				},
				{
					fieldtype: 'Select',
					fieldname: 'period',
					label: __('Pay Period'),
					options: (m.periods || []).map((p) => ({ value: p.value, label: p.label })),
					default: m.default,
					depends_on: 'eval:!doc.resigned',
					mandatory_depends_on: 'eval:!doc.resigned',
					description: __(
						'Employees on the payroll until the end of this period. Not included: those who left before or during it (use Resigned Employees Only), those on maternity leave for the whole period, and Exclude Employees of Attendance Calculation Setting.'
					),
				},
				{
					fieldtype: 'Date',
					fieldname: 'from_date',
					label: __('Relieving Date From'),
					depends_on: 'eval:doc.resigned',
					mandatory_depends_on: 'eval:doc.resigned',
				},
				{
					fieldtype: 'Date',
					fieldname: 'to_date',
					label: __('Relieving Date To'),
					depends_on: 'eval:doc.resigned',
					mandatory_depends_on: 'eval:doc.resigned',
				},
			],
			primary_action_label: __('Download'),
			primary_action: (v) => {
				const q = v.resigned
					? `resigned=1&from_date=${encodeURIComponent(v.from_date)}&to_date=${encodeURIComponent(v.to_date)}`
					: `period=${encodeURIComponent(v.period)}`;
				if (v.resigned && v.from_date > v.to_date) {
					frappe.msgprint(__('Relieving Date From must be on or before Relieving Date To.'));
					return;
				}
				d.hide();
				window.open(`/api/method/${api}.download_template?${q}`);
			},
		});
		d.show();
	});
}
