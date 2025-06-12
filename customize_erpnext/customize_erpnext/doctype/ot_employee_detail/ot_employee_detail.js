// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on('OT Employee Detail', {
	refresh: function(frm) {
		// Set precision for rate_multiplier field
		frm.set_df_property('rate_multiplier', 'precision', 2);
	},
	
	rate_multiplier: function(frm) {
		// Ensure rate_multiplier is properly formatted
		if (frm.doc.rate_multiplier) {
			frm.set_value('rate_multiplier', parseFloat(frm.doc.rate_multiplier).toFixed(2));
		}
		calculate_ot_amount(frm);
	},
	
	ot_level: function(frm) {
		// This will be handled by the parent form's logic
		// since we can't directly access Overtime Level as a separate doctype
		calculate_ot_amount(frm);
	},
	
	basic_hourly_rate: function(frm) {
		calculate_ot_amount(frm);
	},
	
	planned_hours: function(frm) {
		calculate_ot_amount(frm);
	}
});

function calculate_ot_amount(frm) {
	if (frm.doc.basic_hourly_rate && frm.doc.rate_multiplier && frm.doc.planned_hours) {
		let ot_amount = parseFloat(frm.doc.basic_hourly_rate) * 
						parseFloat(frm.doc.rate_multiplier) * 
						parseFloat(frm.doc.planned_hours);
		frm.set_value('ot_amount', ot_amount);
	}
}

