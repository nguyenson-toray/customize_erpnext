frappe.listview_settings["CCTV Tracking"] = {
	onload(listview) {
		listview.page.add_inner_button(__("Run Now"), function () {
			frappe.prompt(
				[
					{
						label: __("NVR"),
						fieldname: "nvr",
						fieldtype: "Link",
						options: "NVR",
						reqd: 0,
						description: __("Leave blank to run all NVRs"),
					},
					{
						label: __("Recipients"),
						fieldname: "recipients",
						fieldtype: "Text",
						default: "son.nt@tiqn.com.vn\nvinh.nt@tiqn.com.vn",
						description: __("One email per line. Leave blank to skip sending email."),
					},
					{ fieldtype: "Column Break" },
					{
						label: __("Gap Check (days)"),
						fieldname: "gap_days",
						fieldtype: "Int",
						default: 7,
						description: __("Number of past days to scan for recording gaps"),
					},
					{
						label: __("Min Gap (minutes)"),
						fieldname: "gap_min_minutes",
						fieldtype: "Int",
						default: 10,
						description: __("Only report gaps longer than this"),
					},
				],
				function (values) {
					const recipients = (values.recipients || "").trim();
					const send_email = recipients.length > 0;
					frappe.show_alert({ message: __("Running monitor..."), indicator: "orange" });
					frappe.call({
						method: values.nvr
							? "customize_erpnext.network.utils.monitor_runner.run_monitor_for_nvr"
							: "customize_erpnext.network.utils.monitor_runner.run_all_nvr",
						args: values.nvr
							? {
								nvr_name: values.nvr,
								send_email,
								recipients,
								gap_days: values.gap_days || 7,
								gap_min_minutes: values.gap_min_minutes || 10,
							  }
							: {
								send_email,
								recipients,
								gap_days: values.gap_days || 7,
								gap_min_minutes: values.gap_min_minutes || 10,
							  },
						type: "POST",
						callback(r) {
							if (!r.exc) {
								frappe.show_alert({
									message: __("Done! New record created."),
									indicator: "green",
								});
								listview.refresh();
							}
						},
					});
				},
				__("Run CCTV Monitor"),
				__("Run Now")
			);
		}, __("Actions"));
	},
};
