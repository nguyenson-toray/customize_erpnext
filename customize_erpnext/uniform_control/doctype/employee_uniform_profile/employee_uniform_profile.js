// Item filters driven by Uniform Setting → Uniform Item Group (no hardcoded group).
frappe.ui.form.on('Employee Uniform Profile', {
	setup(frm) {
		frm.set_query('shirt_item', () => {
			const filters = { has_variants: 1 };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
		frm.set_query('item_template', 'items', () => {
			const filters = { variant_of: ['is', 'not set'] };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
	},
	onload(frm) {
		frappe.db
			.get_single_value('Uniform Setting', 'uniform_item_group')
			.then((v) => (frm._uniform_item_group = v));
	},
});
