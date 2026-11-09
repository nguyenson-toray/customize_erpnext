// Employee Uniform Profile — sizes come from the Employee; Shirt / Cap follow the
// Uniform Rules unless Manual Override is ticked (see uniform_control/utils.py).
frappe.ui.form.on('Employee Uniform Profile', {
	setup(frm) {
		// Item filters driven by Uniform Setting → Uniform Item Group (no hardcoded group)
		frm.set_query('shirt_item', () => {
			const filters = { has_variants: 1 };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
		// Cap: an exact cap variant
		frm.set_query('cap_item', () => {
			const filters = { has_variants: 0, variant_of: ['is', 'set'] };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
	},
	onload(frm) {
		frappe.db
			.get_single_value('Uniform Setting', 'uniform_item_group')
			.then((v) => (frm._uniform_item_group = v));
	},
	refresh(frm) {
		render_assignment(frm);
		if (frm.is_new()) return;

		frm.add_custom_button(__('Edit Sizes on Employee'), () =>
			frappe.set_route('Form', 'Employee', frm.doc.employee)
		);
		// Repair tool: rebuild the tracking tables from submitted allocations
		if (frappe.user.has_role('System Manager')) {
			frm.add_custom_button(
				__('Rebuild Tracking'),
				() => {
					frappe.call({
						method: 'customize_erpnext.uniform_control.api.uniform_api.rebuild_tracking',
						args: { employee: frm.doc.employee },
						freeze: true,
						freeze_message: __('Rebuilding from allocations...'),
						callback(r) {
							const m = r.message || {};
							frappe.show_alert({
								message: __('Tracking rebuilt ({0} item types).', [m.rebuilt || 0]),
								indicator: 'green',
							});
							frm.reload_doc();
						},
					});
				},
				__('Tools')
			);
		}
	},
});

// "What This Employee Gets": one row per category, from __onload.assignment
function render_assignment(frm) {
	const field = frm.fields_dict.assignment_html;
	if (!field) return;
	const a = (frm.doc.__onload || {}).assignment || {};
	const esc = frappe.utils.escape_html;
	const items = a.items || [];
	if (!items.length) {
		field.$wrapper.html(
			`<div class="text-muted small">${frm.is_new() ? '' : __('No Uniform Rule matches this employee.')}</div>`
		);
		return;
	}
	const s = a.sizes || {};
	const sizes = `<div class="small text-muted" style="margin-bottom:6px">
		${__('Gender')}: <b>${esc(s.gender || '—')}</b> ·
		${__('Shirt Size')}: <b>${esc(s.shirt || '—')}</b> ·
		${__('Shoe Size')}: <b>${esc(s.shoe || __('Free Size'))}</b>
		<span> (${__('from the Employee')})</span></div>`;
	const rows = items
		.map((x) => {
			const issue = x.variant
				? esc(x.variant)
				: `<span style="color:var(--red-600)">${esc(x.error || __('Not resolved'))}</span>`;
			const note = x.manual ? `<span class="indicator-pill orange">${__('Manual')}</span>` : '';
			const cycle = x.one_time
				? __('One-time')
				: x.reissue_months
				? __('Every {0} months × {1}', [x.reissue_months, x.reissue_qty])
				: '—';
			return `<tr>
				<td>${esc(__(x.category))}</td>
				<td><a href="/app/uniform-rule/${encodeURIComponent(x.rule)}">${esc(x.rule_item)}</a></td>
				<td><b>${issue}</b> ${note}</td>
				<td class="text-right">${x.first_qty || 0}</td>
				<td>${cycle}</td>
			</tr>`;
		})
		.join('');
	field.$wrapper.html(`${sizes}
		<table class="table table-sm table-bordered" style="margin:0">
			<thead><tr>
				<th>${__('Category')}</th><th>${__('By Rule')}</th><th>${__('Will Issue')}</th>
				<th class="text-right">${__('First Qty')}</th><th>${__('Reissue')}</th>
			</tr></thead>
			<tbody>${rows}</tbody>
		</table>`);
}
