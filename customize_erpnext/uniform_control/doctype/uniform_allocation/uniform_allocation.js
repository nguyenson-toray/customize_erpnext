// Uniform Allocation — fetch eligible employees into the items table using the
// filter fields (uniform type, department, joining date range).
frappe.ui.form.on('Uniform Allocation', {
	setup(frm) {
		// Item filters driven by Uniform Setting → Uniform Item Group (no hardcoded group)
		frm.set_query('uniform_type_filter', () => {
			const filters = { variant_of: ['is', 'not set'] };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
		frm.set_query('item_code', 'items', () => {
			const filters = { has_variants: 0, disabled: 0 };
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
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Get Employees'), () => get_employees(frm));
		}
	},
});

function get_employees(frm) {
	if (!frm.doc.allocation_type) {
		frappe.msgprint(__('Select Allocation Type first.'));
		return;
	}
	const run = () =>
		frappe.call({
			method: 'customize_erpnext.uniform_control.api.uniform_api.get_eligible_employees',
			args: {
				allocation_type: frm.doc.allocation_type,
				uniform_type: frm.doc.uniform_type_filter || null,
				department: frm.doc.department_filter || null,
				group: frm.doc.group_filter || null,
				gender: frm.doc.gender_filter || null,
				joining_date_from: frm.doc.joining_date_from || null,
				joining_date_to: frm.doc.joining_date_to || null,
			},
			freeze: true,
			freeze_message: __('Fetching eligible employees...'),
			callback(r) {
				fill_items(frm, r.message || []);
			},
		});

	if ((frm.doc.items || []).length) {
		frappe.confirm(__('Replace the current items?'), run);
	} else {
		run();
	}
}

function fill_items(frm, rows) {
	const reason_map = { 'New Issue': 'New Issue', 'Supplement': 'Periodic Supplement' };
	const issue_reason = reason_map[frm.doc.allocation_type] || '';

	frm.clear_table('items');
	const skipped = [];
	rows.forEach((r) => {
		if (!r.item_code) {
			skipped.push(`${r.employee} — ${r.item_template}: ${r.item_error || ''}`);
			return;
		}
		const row = frm.add_child('items');
		row.employee = r.employee;
		row.employee_name = r.employee_name;
		row.department = r.department;
		row.item_code = r.item_code;
		row.qty = r.qty;
		row.available_qty = r.available_qty;
		row.issue_reason = issue_reason;
		row.shoe_rack_location = r.shoe_rack_location;
	});
	frm.refresh_field('items');

	if (!rows.length) {
		frappe.msgprint(__('No eligible employees found.'));
		return;
	}
	let msg = __('Added {0} row(s).', [frm.doc.items.length]);
	if (skipped.length) {
		msg += '<br><br>' + __('Skipped {0} row(s) without a resolvable item:', [skipped.length]);
		msg += '<br>' + skipped.map(frappe.utils.escape_html).join('<br>');
	}
	frappe.msgprint(msg);
}
