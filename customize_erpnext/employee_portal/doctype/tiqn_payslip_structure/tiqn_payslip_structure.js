// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// Payslip Structure: the lines of the payslip from a pay period on. A payslip keeps its
// own copy of the lines; "Apply Labels to Payslips" copies changed labels / formula text
// into the payslips of this structure (numbers never change).

const PSS_API = 'customize_erpnext.employee_portal.doctype.tiqn_payslip_structure.tiqn_payslip_structure';

frappe.ui.form.on('TIQN Payslip Structure', {
	refresh(frm) {
		show_periods(frm);
		if (frm.is_new()) return;
		frm.add_custom_button(__('Apply Labels to Payslips'), () => apply_labels(frm));
	},
});

// Pay period "2026-10" = 26/09/2026 - 25/10/2026 (utils.period_bounds).
function period_dates(period) {
	const [y, m] = period.split('-').map(Number);
	const pad = (n) => String(n).padStart(2, '0');
	const prev = m === 1 ? [y - 1, 12] : [y, m - 1];
	return [`${prev[0]}-${pad(prev[1])}-26`, `${y}-${pad(m)}-25`].map((d) => frappe.datetime.str_to_user(d));
}

// Valid To Period is hidden while empty (read-only): the range is spelled out under Valid From.
function show_periods(frm) {
	const { valid_from, valid_to } = frm.doc;
	if (frm.is_new() || !/^\d{4}-\d{2}$/.test(valid_from || '')) return;
	frm.set_df_property(
		'valid_from',
		'description',
		valid_to
			? __('Periods {0} to {1} ({2} - {3}).', [valid_from, valid_to, period_dates(valid_from)[0], period_dates(valid_to)[1]])
			: __('From period {0} ({1}) on, until a structure with a later Valid From Period is created.', [valid_from, period_dates(valid_from)[0]])
	);
}

frappe.ui.form.on('TIQN Payslip Structure Line', {
	code(frm, cdt, cdn) {
		// 2.1 -> under 2, when line 2 exists and nothing was chosen yet.
		const row = locals[cdt][cdn];
		const code = (row.code || '').trim();
		if (row.parent_code || !code.includes('.')) return;
		const parent = code.split('.').slice(0, -1).join('.');
		if ((frm.doc.lines || []).some((r) => r.code === parent)) frappe.model.set_value(cdt, cdn, 'parent_code', parent);
	},
});

function apply_labels(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__('Save the structure first.'));
		return;
	}
	frappe.call({ method: `${PSS_API}.get_label_changes`, args: { name: frm.doc.name }, type: 'GET' }).then((r) => {
		const m = r.message || {};
		if (!m.changes || !m.changes.length) {
			frappe.msgprint(__('The {0} payslip(s) of this structure already have these labels.', [m.payslips || 0]));
			return;
		}
		const esc = frappe.utils.escape_html;
		const rows = m.changes
			.map((c) => `<tr><td>${esc(c.code)}</td><td>${esc(c.field)}</td><td>${esc(c.old)}</td><td>${esc(c.new)}</td><td>${c.payslips}</td></tr>`)
			.join('');
		frappe.confirm(
			`<p>${__('Copy these labels into the payslips of this structure, Published ones included? Amounts, Published On and notifications do not change. Phones that already opened a payslip may keep the old text until their app cache is cleared.')}</p>
			<table class="table table-bordered table-sm"><thead><tr><th>${__('No.')}</th><th>${__('Field')}</th><th>${__('Now')}</th><th>${__('New')}</th><th>${__('Payslips')}</th></tr></thead><tbody>${rows}</tbody></table>`,
			() =>
				frappe.call({ method: `${PSS_API}.apply_labels`, args: { name: frm.doc.name }, freeze: true }).then((res) => {
					const out = res.message || {};
					frappe.show_alert({
						message: out.queued
							? __('Applying labels to {0} payslips in the background.', [out.payslips])
							: __('Labels applied to {0} payslip(s).', [out.changed]),
						indicator: 'green',
					});
					frm.reload_doc();
				})
		);
	});
}
