// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Portal Settings", {
	refresh(frm) {
		// Payslip Lines follow the TIQN Payslip fields (synced on save) - only the
		// Mini App Label is edited, rows are never added or removed by hand.
		const grid = frm.get_field("payslip_lines").grid;
		grid.cannot_add_rows = true;
		grid.df.cannot_delete_rows = 1;
		grid.refresh();
	},
});
