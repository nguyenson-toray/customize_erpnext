// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt
//
// Payslip Upload — C&B imports the salary Excel (one row per employee), checks it,
// imports it as Draft, then publishes a period to the Zalo Mini App.
// Server side: employee_portal/payslip_admin.py.

frappe.pages['payslip-upload'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Payslip Upload'),
		single_column: true,
	});
	new PayslipUploadPage(page);
};

const PSU_API = 'customize_erpnext.employee_portal.payslip_admin';

class PayslipUploadPage {
	constructor(page) {
		this.page = page;
		this.$body = $(`
			<div class="psu">
				<div class="psu-card">
					<div class="psu-card-title">${__('1. Upload the salary Excel file')}</div>
					<div class="text-muted small psu-help">
						${__('One row per employee: No., Period (YYYY-MM or MM-YYYY), Period From, Period To, Pay Date, Employee, Employee Name, Designation, Department, Section, Group, Note (optional free text for the whole payslip), then one column per line of the Payslip Structure of the period, matched by the code at the start of the header (e.g. "3.2 ..."). Download the template of the period to get the right columns. No. and Designation are not imported. Numbers are imported as they are; only impossible ones (negative days / hours, more working days or overtime hours than the period has, mistyped amounts) are refused. Period From / To may be inside the period (joined or left during it); empty Pay Date = the monthly pay day.')}
					</div>
					<div class="psu-actions">
						<button class="btn btn-default btn-sm psu-template">${__('Download Template')}</button>
						<button class="btn btn-primary btn-sm psu-upload">${__('Upload Excel')}</button>
					</div>
					<div class="psu-preview"></div>
				</div>
				<div class="psu-card">
					<div class="psu-card-title">${__('2. Publish to the Mini App')}</div>
					<div class="text-muted small psu-help">
						${__('Employees only see Published payslips. Withdraw hides a period again so it can be corrected and re-uploaded.')}
					</div>
					<div class="psu-periods"></div>
				</div>
			</div>
		`).appendTo(page.body);
		this.inject_css();

		this.$body.find('.psu-template').on('click', () => payslip_template_dialog(PSU_API));
		this.$body.find('.psu-upload').on('click', () => this.upload());
		page.set_secondary_action(__('Refresh'), () => this.load_periods());

		frappe.realtime.on('payslip_delete_done', (data) => {
			frappe.show_alert({ message: __('Deleted {0} payslips of {1}', [data.deleted, data.period]), indicator: 'green' });
			this.load_periods();
		});
		frappe.realtime.on('payslip_import_done', (data) => {
			frappe.show_alert({
				message: __('Imported {0} payslips as Draft (batch {1})', [data.rows, data.batch]),
				indicator: 'green',
			});
			this.load_periods();
		});
		this.load_periods();
	}

	upload() {
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
		const $p = this.$body.find('.psu-preview').html(`<div class="text-muted">${__('Checking...')}</div>`);
		frappe
			.call({ method: `${PSU_API}.preview_upload`, args: { file_url }, freeze: true })
			.then((r) => this.render_preview(r.message))
			.catch(() => $p.empty());
	}

	render_preview(data) {
		const $p = this.$body.find('.psu-preview').empty();
		const esc = frappe.utils.escape_html;
		const rows = data.rows || [];
		const bad = rows.filter((r) => r.errors.length);
		const warn = rows.filter((r) => !r.errors.length && r.warnings.length);

		let html = `<div class="psu-summary">
			<span class="indicator-pill blue">${__('{0} rows', [rows.length])}</span>
			<span class="indicator-pill ${data.error_count ? 'red' : 'green'}">${__('{0} errors', [data.error_count])}</span>
			<span class="indicator-pill ${data.warning_count ? 'orange' : 'green'}">${__('{0} warnings', [data.warning_count])}</span>
			<span class="text-muted">${__('Periods')}: ${(data.periods || []).map(esc).join(', ') || '-'}</span>
			${data.structure ? `<span class="text-muted">${__('Payslip Structure')}: <a href="/app/tiqn-payslip-structure/${encodeURIComponent(data.structure)}" target="_blank">${esc(data.structure)}</a></span>` : ''}
		</div>`;

		if (data.header_errors.length) {
			html += `<div class="psu-block psu-err"><b>${__('File layout')}</b><ul>${data.header_errors
				.map((e) => `<li>${esc(e)}</li>`)
				.join('')}</ul></div>`;
		}
		if (data.missing_components && data.missing_components.length) {
			html += `<div class="psu-block psu-warn">${__('Not in the file (will be empty)')}: ${data.missing_components
				.map(esc)
				.join(', ')}</div>`;
		}
		const issue_rows = bad.concat(warn);
		if (issue_rows.length) {
			html += `<table class="table table-bordered table-sm psu-table"><thead><tr>
				<th>${__('Row')}</th><th>${__('Employee')}</th><th>${__('Period')}</th><th>${__('Issues')}</th>
			</tr></thead><tbody>`;
			for (const r of issue_rows) {
				const items = r.errors
					.map((e) => `<li class="text-danger">${esc(e)}</li>`)
					.concat(r.warnings.map((w) => `<li class="psu-warn-text">${esc(w)}</li>`))
					.join('');
				html += `<tr><td>${r.row}</td><td>${esc(r.employee || r.employee_raw)}<div class="text-muted small">${esc(
					r.employee_name || ''
				)}</div></td><td>${esc(r.period || '')}</td><td><ul class="psu-issues">${items}</ul></td></tr>`;
			}
			html += '</tbody></table>';
		}

		html += `<div class="psu-actions">`;
		if (data.error_count) {
			html += `<span class="text-danger">${__('Fix the errors in Excel and upload again.')}</span>`;
		} else {
			if (data.warning_count) {
				html += `<label class="psu-confirm"><input type="checkbox" class="psu-confirm-box"> ${__(
					'I have checked the warnings above'
				)}</label>`;
			}
			html += `<button class="btn btn-primary btn-sm psu-import" ${data.warning_count ? 'disabled' : ''}>${__(
				'Import {0} payslips as Draft',
				[rows.length]
			)}</button>`;
		}
		html += `<button class="btn btn-default btn-sm psu-discard">${__('Discard')}</button></div>`;
		$p.html(html);

		$p.find('.psu-confirm-box').on('change', (e) => {
			$p.find('.psu-import').prop('disabled', !e.target.checked);
		});
		$p.find('.psu-import').on('click', () => this.do_import(data.warning_count ? 1 : 0));
		$p.find('.psu-discard').on('click', () => {
			frappe.call({ method: `${PSU_API}.discard_upload`, args: { file_url: this.file_url } });
			this.file_url = null;
			$p.empty();
		});
	}

	do_import(confirm_warnings) {
		frappe
			.call({
				method: `${PSU_API}.import_upload`,
				args: { file_url: this.file_url, confirm_warnings },
				freeze: true,
				freeze_message: __('Importing...'),
			})
			.then((r) => {
				const m = r.message;
				this.$body.find('.psu-preview').empty();
				this.file_url = null;
				if (m.queued) {
					frappe.show_alert({
						message: __('{0} rows are being imported in the background. This page refreshes when done.', [m.rows]),
						indicator: 'blue',
					});
				} else {
					frappe.show_alert({ message: __('Imported {0} payslips as Draft', [m.rows]), indicator: 'green' });
					this.load_periods();
				}
			});
	}

	load_periods() {
		frappe.call({ method: `${PSU_API}.get_period_summary`, type: 'GET' }).then((r) => this.render_periods(r.message || []));
		frappe.call({ method: `${PSU_API}.get_config_errors`, type: 'GET' }).then((r) => {
			const errors = r.message || [];
			this.$body.find('.psu-config').remove();
			if (!errors.length) return;
			$(`<div class="psu-block psu-err psu-config"><b>${__('Payslip setup')}</b><ul class="psu-issues">${errors
				.map((e) => `<li>${frappe.utils.escape_html(e)}</li>`)
				.join('')}</ul></div>`).prependTo(this.$body);
		});
	}

	render_periods(periods) {
		const $w = this.$body.find('.psu-periods').empty();
		if (!periods.length) {
			$w.html(`<div class="text-muted">${__('No payslips yet.')}</div>`);
			return;
		}
		const fmt_money = (v) => format_number(v, null, 0);
		let html = `<table class="table table-bordered table-sm psu-table"><thead><tr>
			<th>${__('Period')}</th><th>${__('Draft')}</th><th>${__('Published', null, 'Payslip')}</th><th>${__('Withdrawn', null, 'Payslip')}</th>
			<th>${__('Final Settlement')}</th><th>${__('Net Pay Total')}</th><th>${__('Viewed', null, 'Payslip')}</th><th></th>
		</tr></thead><tbody>`;
		for (const p of periods) {
			const range = `${frappe.datetime.str_to_user(p.from_date)} – ${frappe.datetime.str_to_user(p.to_date)}`;
			html += `<tr data-period="${p.period}">
				<td><a href="/app/tiqn-payslip?period=${encodeURIComponent(p.period)}"><b>${p.period}</b></a>
					<div class="text-muted small">${range}</div></td>
				<td>${p.Draft}</td><td>${p.Published}</td><td>${p.Withdrawn}</td><td>${p.final_settlement || '-'}</td>
				<td class="text-right">${fmt_money(p.net_total)}</td>
				<td>${p.Published ? `${p.viewed} / ${p.Published}` : '-'}</td>
				<td class="psu-row-actions">
					${p.Draft + p.Withdrawn ? `<button class="btn btn-primary btn-xs psu-publish">${__('Publish', null, 'Payslip')}</button>` : ''}
					${p.Published ? `<button class="btn btn-default btn-xs psu-withdraw">${__('Withdraw', null, 'Payslip')}</button>` : ''}
					${p.Draft + p.Withdrawn ? `<button class="btn btn-default btn-xs psu-delete">${__('Delete Payslips')}</button>` : ''}
				</td></tr>`;
		}
		html += '</tbody></table>';
		$w.html(html);
		const by_period = {};
		for (const p of periods) by_period[p.period] = p;

		const act = (cls, method, question, done) => {
			$w.find(cls).on('click', (e) => {
				const period = $(e.target).closest('tr').data('period');
				frappe.confirm(question(period, by_period[period]), () => {
					frappe
						.call({ method: `${PSU_API}.${method}`, args: { period }, freeze: true })
						.then((r) => {
							frappe.show_alert({ message: done(r.message), indicator: 'green' });
							this.load_periods();
						});
				});
			});
		};
		act(
			'.psu-publish',
			'publish_period',
			(p) => __('Publish all Draft payslips of {0}? Employees will see them in the Mini App immediately. Final settlements alone send no notification.', [p]),
			(m) => (m.notified ? __('Published {0} payslips', [m.published]) : __('Published {0} payslips, no notification sent', [m.published]))
		);
		act(
			'.psu-withdraw',
			'withdraw_period',
			(p) => __('Withdraw all published payslips of {0}? They disappear from the Mini App until published again.', [p]),
			(m) => __('Withdrew {0} payslips', [m.withdrawn])
		);
		act(
			'.psu-delete',
			'delete_period',
			(p, row) => {
				let q = __('Delete all {0} Draft / Withdrawn payslips of {1} ({2} Draft, {3} Withdrawn)? Published payslips are not touched.', [
					row.Draft + row.Withdrawn,
					p,
					row.Draft,
					row.Withdrawn,
				]);
				if (row.Withdrawn) {
					q += `<br><br><b class="psu-warn-text">${__('{0} Withdrawn payslips were published before; {1} of them were opened by the employee. Deleting removes that record too.', [
						row.Withdrawn,
						row.withdrawn_viewed || 0,
					])}</b>`;
				}
				return q;
			},
			(m) => (m.queued ? __('Deleting {0} payslips in the background', [m.deleted]) : __('Deleted {0} payslips', [m.deleted]))
		);
	}

	inject_css() {
		if (document.getElementById('psu-css')) return;
		const style = document.createElement('style');
		style.id = 'psu-css';
		style.textContent = `
			.psu { display: flex; flex-direction: column; gap: 16px; padding: 8px 0 32px; }
			.psu-card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--border-radius-md); padding: 16px; }
			.psu-card-title { font-weight: 600; margin-bottom: 4px; }
			.psu-help { margin-bottom: 12px; }
			.psu-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
			.psu-summary { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-top: 16px; }
			.psu-block { margin-top: 12px; padding: 8px 12px; border-radius: var(--border-radius); }
			.psu-err { background: var(--red-50, #fff5f5); color: var(--red-700, #c53030); }
			.psu-warn { background: var(--orange-50, #fffaf0); color: var(--orange-700, #b7791f); }
			.psu-warn-text { color: var(--orange-600, #b7791f); }
			.psu-table { margin-top: 12px; margin-bottom: 0; }
			.psu-issues { margin: 0; padding-left: 16px; }
			.psu-row-actions { white-space: nowrap; }
			.psu-row-actions .btn { margin-right: 4px; }
			.psu-confirm { margin: 0; display: flex; gap: 6px; align-items: center; font-weight: normal; }
		`;
		document.head.appendChild(style);
	}
}

// "Download Template": monthly (pick the pay period) or resigned employees of a period
// (relieving date range inside it) - employee columns pre-filled, HR types the numbers.
function payslip_template_dialog(api) {
	frappe.call({ method: `${api}.get_template_periods`, type: 'GET' }).then((r) => {
		const m = r.message || {};
		const bounds = (period) => (m.periods || []).find((p) => p.value === period) || {};
		// Resigned mode: the relieving date range starts as the whole period, HR may narrow it.
		// `d` is assigned below; onchange may fire while the dialog is still being built.
		let d = null;
		const reset_range = () => {
			if (!d) return;
			const b = bounds(d.get_value('period'));
			d.set_value('from_date', b.from_date || '');
			d.set_value('to_date', b.to_date || '');
		};
		d = new frappe.ui.Dialog({
			title: __('Download Template'),
			fields: [
				{
					fieldtype: 'Check',
					fieldname: 'resigned',
					label: __('Resigned Employees Only'),
					description: __(
						'Employees whose relieving date is in the selected period (range below), paid separately within 14 days of leaving. Period To = the day before the relieving date; Pay Date is filled in. Those leaving on the day after the period ends worked the whole period and are on the monthly template.'
					),
					onchange: () => reset_range(),
				},
				{
					fieldtype: 'Select',
					fieldname: 'period',
					label: __('Pay Period'),
					options: (m.periods || []).map((p) => ({ value: p.value, label: p.label })),
					default: m.default,
					reqd: 1,
					description: __(
						'Monthly: employees on the payroll until the end of this period. Not included: those who left before or during it (use Resigned Employees Only), those on maternity leave for the whole period, and Exclude Employees of Attendance Calculation Setting.'
					),
					onchange: () => reset_range(),
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
					description: __('Must be inside the selected period.'),
				},
			],
			primary_action_label: __('Download'),
			primary_action: (v) => {
				let q = `period=${encodeURIComponent(v.period)}`;
				if (v.resigned) {
					const b = bounds(v.period);
					if (v.from_date > v.to_date || v.from_date < b.from_date || v.to_date > b.to_date) {
						frappe.msgprint(
							__('The relieving date range must be inside the selected period ({0} - {1}), From on or before To.', [
								frappe.datetime.str_to_user(b.from_date),
								frappe.datetime.str_to_user(b.to_date),
							])
						);
						return;
					}
					q += `&resigned=1&from_date=${encodeURIComponent(v.from_date)}&to_date=${encodeURIComponent(v.to_date)}`;
				}
				d.hide();
				window.open(`/api/method/${api}.download_template?${q}`);
			},
		});
		d.show();
		reset_range();
	});
}
