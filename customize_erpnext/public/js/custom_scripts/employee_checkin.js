frappe.ui.form.on("Employee Checkin", {
	refresh: async (frm) => {
		if (frm.doc.__islocal) {
			// set custom_reason_for_manual_check_in is mandotory if add "Employee Checkin"  manually
			frm.set_df_property(
				"custom_reason_for_manual_check_in",
				"reqd",
				1
			);
			// remove first option of custom_reason_for_manual_check_in
			frm.set_df_property(
				"custom_reason_for_manual_check_in",
				"options",
				[
					"First Working Day",
					"Forget Check In/Out",
					"Machine Error",
					"Other"
				]
			);
			frm.set_df_property("skip_auto_attendance", "hidden", 1);
			frm.set_df_property("log_type", "hidden", 1);
			frm.set_df_property("employee", "read_only", 0);
			frm.set_df_property("time", "read_only", 0);
			frm.set_df_property("device_id", "read_only", 1);
			frm.set_df_property("custom_reason_for_manual_check_in", "read_only", 0);
		}

		// Add Update Fields button for saved documents
		if (!frm.doc.__islocal) {
			// Remove default HRMS "Fetch Shift" button (with delay to ensure it's removed)
			setTimeout(() => {
				frm.remove_custom_button(__('Fetch Shift'));
			}, 100);

			// Add our custom Update Fields button
			frm.add_custom_button(__('🔄 Update Fields'), function() {
				update_current_checkin(frm);
			});
		}

		// Listen for realtime updates to reload form when log_type is auto-set
		frappe.realtime.on("employee_checkin_updated", function (data) {
			if (data.current_doc === frm.doc.name) {
				frm.reload_doc();
			}
		});
	},

	onload: function (frm) {
		// Setup realtime listener on form load
		if (!frm.realtime_listener_setup) {
			frappe.realtime.on("employee_checkin_updated", function (data) {
				if (frm.doc.name && data.current_doc === frm.doc.name) {
					frm.reload_doc();
				}
			});
			frm.realtime_listener_setup = true;
		}
	}

});

function update_current_checkin(frm) {
	if (!frm.doc.time) {
		frappe.msgprint({
			title: __('Missing Time'),
			message: __('Cannot update checkin without time field'),
			indicator: 'red'
		});
		return;
	}

	// Get the date from the checkin time
	let checkin_date = frappe.datetime.str_to_obj(frm.doc.time).toISOString().split('T')[0];

	frappe.confirm(
		__('Update fields (Shift, Log Type, Offshift) for this checkin?'),
		function() {
			// User confirmed, proceed with update
			frappe.call({
				method: 'customize_erpnext.overrides.employee_checkin.employee_checkin.bulk_update_employee_checkin',
				args: {
					from_date: checkin_date,
					to_date: checkin_date
				},
				freeze: true,
				freeze_message: __('Updating checkin...'),
				callback: function(r) {
					if (r.message !== undefined && r.message > 0) {
						frappe.show_alert({
							message: __('Checkin updated successfully'),
							indicator: 'green'
						});

						// Reload the form to show updated values
						frm.reload_doc();
					} else {
						frappe.show_alert({
							message: __('No updates needed - fields are already set'),
							indicator: 'blue'
						});
					}
				},
				error: function(r) {
					frappe.msgprint({
						title: __('Update Failed'),
						message: __('An error occurred while updating checkin. Please check the error log.'),
						indicator: 'red'
					});
				}
			});
		}
	);
}
