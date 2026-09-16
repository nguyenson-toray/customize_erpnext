// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on('TIQN Vehicle Trip', {
	vehicle(frm) {
		// The server fills a blank driver in validate() anyway - this is so the
		// Desk user SEES who will drive before saving, instead of the field
		// changing under them after the save.
		if (!frm.doc.vehicle || frm.doc.driver) return;

		frappe.db.get_value(
			'TIQN Driver',
			{ assigned_vehicle: frm.doc.vehicle, is_active: 1 },
			'name',
			(r) => {
				if (r && r.name) frm.set_value('driver', r.name);
			}
		);
	},
});
