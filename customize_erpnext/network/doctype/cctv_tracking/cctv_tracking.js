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
						description: __("Để trống để chạy tất cả NVR"),
					},
				],
				function (values) {
					frappe.show_alert({
						message: __("Đang chạy giám sát..."),
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
									message: __("Hoàn tất! Đã tạo bản ghi mới."),
									indicator: "green",
								});
								listview.refresh();
							}
						},
					});
				},
				__("Chọn NVR"),
				__("Chạy ngay")
			);
		}, __("Actions"));
	},
};
