// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports['Portal Readiness'] = {
	filters: [
		{
			fieldname: 'issue',
			label: __('Issue'),
			fieldtype: 'Select',
			options: [
				'',
				'No Phone',
				'Shared Phone',
				'No Leave Approver',
				'Approver Cannot Log In',
				'Never Signed In',
				'Waiting for Phone',
				'Phone Not Found',
			].join('\n'),
		},
	],
};
