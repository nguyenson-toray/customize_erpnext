// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Maternity", {
	refresh(frm) {
		// Set field properties based on type
		toggle_maternity_leave_fields(frm);
	},

	type(frm) {
		toggle_maternity_leave_fields(frm);

		// Auto-set apply_benefit = 1 when type = 'Pregnant'
		if (frm.doc.type === 'Pregnant') {
			frm.set_value('apply_benefit', 1);
		}
	},

	from_date(frm) {
		validate_date_sequence(frm);
	},

	to_date(frm) {
		validate_date_sequence(frm);
	},

	estimated_due_date(frm) {
		validate_date_sequence(frm);
	},

	validate(frm) {
		validate_date_sequence(frm);
	}
});

function toggle_maternity_leave_fields(frm) {
	const is_maternity_leave = frm.doc.type === 'Maternity Leave';

	// Make key fields readonly when type is Maternity Leave
	frm.set_df_property('employee', 'read_only', is_maternity_leave ? 1 : 0);
	frm.set_df_property('type', 'read_only', is_maternity_leave ? 1 : 0);
}

function validate_date_sequence(frm) {
	if (!frm.doc.from_date) return true;

	const from_date = frappe.datetime.str_to_obj(frm.doc.from_date);

	// Must have to_date or estimated_due_date
	if (!frm.doc.to_date && !frm.doc.estimated_due_date) {
		frappe.msgprint({
			title: __('Missing End Date'),
			message: __('Please set either To Date or Estimated Due Date'),
			indicator: 'red'
		});
		frappe.validated = false;
		return false;
	}

	// Validate to_date > from_date
	if (frm.doc.to_date) {
		const to_date = frappe.datetime.str_to_obj(frm.doc.to_date);
		if (from_date >= to_date) {
			frappe.msgprint({
				title: __('Invalid Date Range'),
				message: __('To Date must be after From Date'),
				indicator: 'red'
			});
			frm.set_value('to_date', '');
			frappe.validated = false;
			return false;
		}
	}

	// Validate estimated_due_date > from_date
	if (frm.doc.estimated_due_date) {
		const estimated_due_date = frappe.datetime.str_to_obj(frm.doc.estimated_due_date);
		if (from_date >= estimated_due_date) {
			frappe.msgprint({
				title: __('Invalid Date Range'),
				message: __('Estimated Due Date must be after From Date'),
				indicator: 'red'
			});
			frm.set_value('estimated_due_date', '');
			frappe.validated = false;
			return false;
		}
	}

	return true;
}
