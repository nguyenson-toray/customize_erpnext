// Policy item filter driven by Uniform Item Group on this form (no hardcoded group).
frappe.ui.form.on('Uniform Setting', {
	setup(frm) {
		frm.set_query('item_template', 'policies', () => {
			const filters = { variant_of: ['is', 'not set'] };
			if (frm.doc.uniform_item_group) filters.item_group = frm.doc.uniform_item_group;
			return { filters };
		});
	},
});
