// Uniform Setting — rule item filters by Category + Uniform Item Group.
frappe.ui.form.on('Uniform Setting', {
	setup(frm) {
		frm.set_query('item', 'rules', (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			const filters = {};
			if (frm.doc.uniform_item_group) filters.item_group = frm.doc.uniform_item_group;
			if (row.category === 'Cap') {
				// exact variant
				filters.has_variants = 0;
				filters.variant_of = ['is', 'set'];
			} else if (row.category === 'Bottle') {
				filters.has_variants = 0;
			} else if (row.category === 'Shirt' || row.category === 'Shoe') {
				// a template
				filters.has_variants = 1;
			}
			return { filters };
		});
	},
	refresh(frm) {
		frm.add_custom_button(__('Apply Defaults to All'), () => {
			frappe.confirm(
				__('Apply default rules to all profiles without Manual Override?'),
				() => {
					frappe.call({
						method: 'customize_erpnext.uniform_control.api.uniform_api.apply_default_rules',
						freeze: true,
						freeze_message: __('Applying default rules...'),
						callback(r) {
							const m = r.message || {};
							frappe.msgprint(
								__('Updated {0} of {1} profiles.', [m.changed || 0, m.profiles || 0])
							);
						},
					});
				}
			);
		});

		frm.add_custom_button(__('Send Alert Now'), () => {
			frappe.call({
				method: 'customize_erpnext.uniform_control.api.uniform_scheduler.send_uniform_alert_now',
				freeze: true,
				freeze_message: __('Sending alert...'),
				callback(r) {
					const m = r.message || {};
					if (m.sent) {
						frappe.show_alert({
							message: __('Alert sent to {0} recipient(s) — {1} short, {2} due.', [
								(m.recipients || []).length,
								m.short || 0,
								m.due || 0,
							]),
							indicator: 'green',
						});
					} else {
						const reason = {
							no_recipients: __('No Alert Recipients configured.'),
							nothing_to_alert: __('Nothing to alert (no low stock / due employees).'),
							disabled: __('Weekly Alert is disabled.'),
						};
						frappe.msgprint(reason[m.reason] || __('Alert not sent.'));
					}
				},
			});
		});
	},
});
