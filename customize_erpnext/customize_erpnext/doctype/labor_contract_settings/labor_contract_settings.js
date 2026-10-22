// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on('Labor Contract Settings', {
	refresh(frm) {
		frm.add_custom_button(__('Send Weekly Email Now'), () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__('Save the settings first.'));
				return;
			}
			frappe.confirm(
				__('Send the weekly contract email now to: {0}?', [frappe.utils.escape_html(frm.doc.weekly_email_recipients || '')]),
				() => frappe.call({
					method: 'customize_erpnext.customize_erpnext.doctype.labor_contract_settings.labor_contract_settings.send_weekly_email_now',
					freeze: true,
					callback: (r) => r.message && frappe.show_alert({ message: r.message, indicator: 'green' }, 7),
				})
			);
		});
	},
});
