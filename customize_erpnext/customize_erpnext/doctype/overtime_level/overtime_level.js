// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Overtime Level", {
	// refresh(frm) {
	// 	// Thông báo cho user về format số
	// 	if (frappe.boot.sysdefaults.number_format && frappe.boot.sysdefaults.number_format.includes(',')) {
	// 		frm.dashboard.add_comment(__('Note: Use comma (,) as decimal separator. Example: 1,5 instead of 1.5'), 'blue', true);
	// 	}
	// },
	
	rate_multiplier(frm) {
		if (frm.doc.rate_multiplier) {
			// Normalize input - chấp nhận cả dấu chấm và phẩy
			let value = String(frm.doc.rate_multiplier);
			if (value.includes('.') && !value.includes(',')) {
				// Nếu user nhập dấu chấm, convert sang format hiện tại
				let number_format = frappe.boot.sysdefaults.number_format || "#,###.##";
				if (number_format.includes(',##')) {
					// Locale sử dụng dấu phẩy làm decimal
					value = value.replace('.', ',');
					frm.set_value('rate_multiplier', value);
				}
			}
		}
	}
});
