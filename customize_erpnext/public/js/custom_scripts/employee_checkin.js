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
	},

});
