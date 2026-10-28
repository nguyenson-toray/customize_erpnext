// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// "Download PDF": the paper payslip as an A4 PDF (employee_portal.payslip_print), named
// {Period}_{section}_{group}_{employee}_{employee_name}.pdf. Draft / Withdrawn print with
// a "BẢN NHÁP / DRAFT" watermark. The list's Download PDF builds many in the background
// (payslip_print.start_pdf_job).
//
// Detail tab: the payslip's own copy of its lines (lines_json, Payslip Structure). A Draft /
// Withdrawn payslip can have its numbers corrected here; the server re-checks them on save.

frappe.ui.form.on('TIQN Payslip', {
	refresh(frm) {
		render_lines(frm);
		if (frm.is_new() || !frappe.user.has_role(['CnB', 'System Manager'])) return;
		frm.add_custom_button(__('Download PDF'), () => {
			// POST + CSRF; the browser downloads the file.
			open_url_post(frappe.request.url, {
				cmd: 'customize_erpnext.employee_portal.payslip_print.download_pdf',
				names: JSON.stringify([frm.doc.name]),
			});
		});
	},
	lines_json(frm) {
		render_lines(frm);
	},
});

function render_lines(frm) {
	const field = frm.get_field('lines_html');
	if (!field) return;
	let lines = [];
	try {
		lines = JSON.parse(frm.doc.lines_json || '[]');
	} catch (e) {
		lines = [];
	}
	if (!lines.length) {
		field.$wrapper.html(`<p class="text-muted">${__('The lines are filled in from the Payslip Structure of the period when the payslip is saved.')}</p>`);
		return;
	}
	const editable = frm.doc.status !== 'Published' && frm.perm[0] && frm.perm[0].write;
	const esc = frappe.utils.escape_html;
	const qty_unit = (l) => (l.unit !== 'VND' ? l.unit : l.quantity_unit);
	const cell = (l, key) => {
		const value = l[key];
		if (value === null || value === undefined) return '';
		if (editable) {
			return `<input type="number" step="any" class="form-control input-xs text-right" data-code="${esc(l.code)}" data-key="${key}" value="${value}">`;
		}
		return key === 'amount' ? format_currency(value, 'VND', 0) : esc(String(value));
	};
	const rows = lines
		.map((l) => {
			const label = `${esc(l.label_en || '')}${l.label_vi ? ` / <i>${esc(l.label_vi)}</i>` : ''}${l.formula_display ? ` (${esc(l.formula_display)})` : ''}`;
			const unit = qty_unit(l) ? __(qty_unit(l) === 'Day' ? 'Days' : 'Hours') : '';
			return `<tr class="${l.is_header ? 'font-weight-bold' : ''}">
				<td>${esc(l.code)}</td>
				<td style="padding-left: ${8 + 16 * (l.level || 0)}px">${label}</td>
				<td class="text-right" style="width: 120px">${cell(l, 'quantity')}</td>
				<td class="text-muted" style="width: 60px">${unit}</td>
				<td class="text-right" style="width: 160px">${cell(l, 'amount')}</td>
			</tr>`;
		})
		.join('');
	field.$wrapper.html(`
		<div class="text-muted small" style="margin-bottom: 6px">${
			editable
				? __('Numbers as HR computed them - nothing is recalculated. Save to keep a change.')
				: __('Published: withdraw the period on the Payslip Upload page to change a number.')
		}</div>
		<table class="table table-bordered table-sm">
			<thead><tr><th style="width: 60px">${__('No.')}</th><th>${__('Line')}</th><th class="text-right">${__('Unit/ĐVT')}</th><th></th><th class="text-right">${__('Amount')} (VND)</th></tr></thead>
			<tbody>${rows}</tbody>
		</table>`);
	if (!editable) return;
	field.$wrapper.find('input').on('change', function () {
		const code = $(this).attr('data-code');
		const key = $(this).attr('data-key');
		const value = this.value === '' ? 0 : flt(this.value);
		const current = JSON.parse(frm.doc.lines_json || '[]');
		const line = current.find((l) => l.code === code);
		if (!line) return;
		line[key] = value;
		// set_value would re-render and drop the focus; the server rebuilds the snapshot on save.
		frm.doc.lines_json = JSON.stringify(current);
		frm.dirty();
	});
}
