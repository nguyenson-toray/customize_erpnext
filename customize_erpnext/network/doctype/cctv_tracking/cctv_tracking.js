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
				],
				function (values) {
					frappe.show_alert({
						message: __("Running monitor..."),
						indicator: "orange",
					});
					frappe.call({
						method: values.nvr
							? "customize_erpnext.network.utils.monitor_runner.run_monitor_for_nvr"
							: "customize_erpnext.network.utils.monitor_runner.run_all_nvr",
						args: values.nvr ? { nvr_name: values.nvr } : {},
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
				__("Select NVR"),
				__("Run Now")
			);
		}, __("Actions"));
	},
};
