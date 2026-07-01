// Uniform Rule — filter the Item link by Category + Uniform Item Group.
frappe.ui.form.on('Uniform Rule', {
	setup(frm) {
		frappe.db.get_single_value('Uniform Setting', 'uniform_item_group')
			.then((g) => { frm._uniform_item_group = g; });
		frm.set_query('item', () => {
			const filters = {};
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			if (frm.doc.category === 'Cap') {
				filters.has_variants = 0;
				filters.variant_of = ['is', 'set'];
			} else if (frm.doc.category === 'Bottle') {
				filters.has_variants = 0;
			} else if (frm.doc.category === 'Shirt' || frm.doc.category === 'Shoe') {
				filters.has_variants = 1;
			}
			return { filters };
		});
	},
	category(frm) {
		frm.set_value('item', null);
	},
});
