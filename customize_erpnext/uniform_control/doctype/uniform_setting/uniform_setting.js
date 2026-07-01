// Uniform Setting — bulk actions. Rules are managed in the standalone
// "Uniform Rule" DocType (item filter lives on its own form).
frappe.ui.form.on('Uniform Setting', {
	refresh(frm) {
		frm.add_custom_button(__('Manage Uniform Rules'), () => frappe.set_route('List', 'Uniform Rule'));

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
