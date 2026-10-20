// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("TIQN Quiz Response", {
	refresh(frm) {
		// Read-only record: created and graded by the quiz page.
		frm.disable_save();
	},
});
