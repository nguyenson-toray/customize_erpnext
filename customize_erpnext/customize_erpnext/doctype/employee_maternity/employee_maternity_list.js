frappe.listview_settings["Employee Maternity"] = {
	add_fields: ["status"],

	get_indicator(doc) {
		// Bảng màu để TRONG hàm có chủ đích: `*_list.js` được nạp thẳng vào global scope
		// của desk, khai báo `const` ở top-level mà trùng tên với một file list khác là
		// "Identifier has already been declared" và vỡ cả trang list.
		//
		// Màu phải khớp `employee_status_sync.PHASE_INDICATOR` — cùng một trạng thái mà
		// pill trên form Employee (`custom_sub_status`) một màu, list một màu khác thì
		// rất khó chịu. Sửa một bên phải sửa bên kia.
		const color = {
			"Pregnant": "blue",
			"Maternity Leave": "orange",
			"Young Child": "green",
			"Inactive": "gray",
		}[doc.status];

		// Status rỗng = chưa rơi vào giai đoạn nào. Cố ý KHÔNG trả indicator: để trống
		// còn phân biệt được với `Inactive` (hồ sơ đã đóng), vốn cũng màu xám.
		if (!color) return;
		return [__(doc.status), color, `status,=,${doc.status}`];
	},

	onload(listview) {
		// ── Button: Calculate Status ────────────────────────────────
		listview.page.add_inner_button(__("Calculate Status"), () => {
			const selected = listview.get_checked_items();
			const names = selected.length ? selected.map(r => r.name) : null;

			const freeze_msg = names
				? __("Calculating status for {0} selected records...", [names.length])
				: __("Calculating status for all records...");

			frappe.call({
				method: "customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.calculate_all_maternity_statuses",
				type: "POST",
				args: names ? { names: JSON.stringify(names) } : {},
				freeze: true,
				freeze_message: freeze_msg,
				callback(r) {
					if (r.message) {
						const { updated, total } = r.message;
						frappe.show_alert({
							message: __("Updated {0} / {1} records", [updated, total]),
							indicator: "green",
						});
						listview.refresh();
					}
				},
			});
		});

		// ── Button: Show Invalid Records ────────────────────────────
		listview.page.add_inner_button(__("Show Invalid Records"), () => {
			frappe.call({
				method: "customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.get_invalid_maternity_records",
				freeze: true,
				freeze_message: __("Checking records..."),
				callback(r) {
					const records = r.message || [];

					if (!records.length) {
						frappe.show_alert({ message: __("All records are valid"), indicator: "green" });
						return;
					}

					let rows_html = records.map(rec => {
						const url = `/app/employee-maternity/${encodeURIComponent(rec.name)}`;
						const issues_html = rec.issues
							.map(i => `<div class="text-danger small">${frappe.utils.escape_html(i)}</div>`)
							.join("");
						return `<tr>
							<td>
								<a href="${url}" target="_blank" rel="noopener"
								   style="white-space:nowrap">
									${frappe.utils.escape_html(rec.name)}
									<i class="fa fa-external-link fa-xs ms-1"></i>
								</a>
							</td>
							<td>${frappe.utils.escape_html(rec.employee)}</td>
							<td>${frappe.utils.escape_html(rec.employee_name)}</td>
							<td>${issues_html}</td>
						</tr>`;
					}).join("");

					const d = new frappe.ui.Dialog({
						title: __("Invalid Records — {0} found", [records.length]),
						size: "extra-large",
					});

					d.$wrapper.find(".modal-body").html(`
						<div style="overflow-x:auto">
							<table class="table table-bordered table-sm table-hover">
								<thead class="table-light">
									<tr>
										<th>${__("Record")}</th>
										<th>${__("Employee ID")}</th>
										<th>${__("Full Name")}</th>
										<th>${__("Issues")}</th>
									</tr>
								</thead>
								<tbody>${rows_html}</tbody>
							</table>
						</div>
					`);
					d.show();
				},
			});
		});
	},
};
