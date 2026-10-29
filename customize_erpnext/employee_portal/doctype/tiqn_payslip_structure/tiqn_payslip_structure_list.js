// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings['TIQN Payslip Structure'] = {
	formatters: {
		// Empty Valid To = no later structure yet.
		valid_to: (value) => value || __('Ongoing'),
	},
};
