// Item filters driven by Uniform Setting → Uniform Item Group (no hardcoded group).
frappe.ui.form.on('Employee Uniform Profile', {
	setup(frm) {
		frm.set_query('shirt_item', () => {
			const filters = { has_variants: 1 };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
		// Cap: an exact Mũ variant (a child item with variants)
		frm.set_query('cap_item', () => {
			const filters = { has_variants: 0, variant_of: ['is', 'set'] };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
		// Issuance Tracking holds the exact variant issued
		frm.set_query('item_template', 'items', () => {
			const filters = { has_variants: 0 };
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
		if (!frm.is_new()) {
			frm.add_custom_button(__('Apply Defaults'), () => {
				frappe.call({
					method: 'customize_erpnext.uniform_control.api.uniform_api.apply_default_rules',
					args: { employee: frm.doc.employee },
					freeze: true,
					callback() {
						frappe.show_alert({ message: __('Defaults applied'), indicator: 'green' });
						frm.reload_doc();
					},
				});
			});
		}
	},
});
