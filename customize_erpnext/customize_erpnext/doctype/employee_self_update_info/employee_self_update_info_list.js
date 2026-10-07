// Copyright (c) 2026, TIQN and contributors
// For license information, please see license.txt

frappe.listview_settings["Employee Self Update Info"] = {
	add_fields: ["status"],
	get_indicator(doc) {
		const map = {
			Submitted: "green",
			Reviewed: "blue",
			Synced: "gray",
			Draft: "orange",
		};
		const color = map[doc.status] || "orange";
		return [__(doc.status), color, "status,=," + doc.status];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Download Excel"), () => _esui_excel_dialog(listview));

		// "Mark Reviewed" chỉ hiện khi Setting KHÔNG bật Disable Review.
		frappe.db.get_single_value("Employee Self Update Info Setting", "disable_review").then((dr) => {
			if (!cint(dr)) {
				listview.page.add_inner_button(__("Mark Reviewed"), () => {
					const names = listview.get_checked_items().map((d) => d.name);
					if (!names.length) {
						frappe.msgprint(__("Select at least one record."));
						return;
					}
					frappe.confirm(__("Mark {0} record(s) as Reviewed?", [names.length]), () => {
						frappe.call({
							method: "customize_erpnext.api.self_update_info.self_update_info_api.review_forms",
							type: "POST",
							args: { names: JSON.stringify(names) },
							freeze: true,
							freeze_message: __("Reviewing..."),
							callback(r) {
								if (!r.message) return;
								esui_show_result(__("Review Result"),
									__("Reviewed: {0} · Skipped: {1}", [r.message.reviewed, r.message.skipped]),
									r.message.results);
								listview.refresh();
							},
						});
					});
				});
			}
		});

		listview.page.add_inner_button(__("Sync to Employee"), () => {
			const names = listview.get_checked_items().map((d) => d.name);
			if (!names.length) {
				frappe.msgprint(__("Select at least one record."));
				return;
			}
			esui_batch_sync_dialog(names, () => listview.refresh());
		});
	},
};

// Batch sync dialog: pick which fields to write (all pre-checked).
function esui_batch_sync_dialog(names, after) {
	frappe.call({
		method: "customize_erpnext.api.self_update_info.self_update_info_api.get_syncable_fields",
		callback(r) {
			const opts = (r.message || []).map((f) => ({ label: f.label, value: f.fieldname, checked: 1 }));
			if (!opts.length) {
				frappe.msgprint(__("No syncable fields are configured."));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Sync to Employee — {0} record(s)", [names.length]),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						options: `<div class="text-muted" style="margin-bottom:6px">${__(
							"Select the fields to write into Employee. Applied to every selected record where the field is present."
						)}</div>`,
					},
					{ fieldtype: "MultiCheck", fieldname: "fields", options: opts, columns: 2 },
				],
				primary_action_label: __("Sync"),
				primary_action() {
					const sel = d.get_value("fields") || [];
					if (!sel.length) {
						frappe.msgprint(__("Select at least one field."));
						return;
					}
					d.hide();
					esui_run_sync(names, sel, after);
				},
			});
			esui_add_toggle_all(d);
			d.show();
		},
	});
}

// Add a "Select all / none" toggle above a MultiCheck dialog.
function esui_add_toggle_all(d) {
	d.$wrapper.find(".modal-header").append(
		`<button class="btn btn-xs btn-default esui-toggle-all" style="margin:10px 0 0 15px">${__("Select all / none")}</button>`
	);
	d.$wrapper.find(".esui-toggle-all").on("click", () => {
		const boxes = d.$wrapper.find('[data-fieldname="fields"] input[type="checkbox"]');
		const anyOff = boxes.filter((i, el) => !el.checked).length > 0;
		boxes.prop("checked", anyOff).trigger("change");
	});
}

// Run sync and render the result dialog. Shared by list + form view.
function esui_run_sync(names, fields, after) {
	frappe.call({
		method: "customize_erpnext.api.self_update_info.self_update_info_api.sync_to_employee",
		type: "POST",
		args: { names: JSON.stringify(names), fields: JSON.stringify(fields || null) },
		freeze: true,
		freeze_message: __("Syncing to Employee..."),
		callback(r) {
			if (!r.message) return;
			const m = r.message;
			esui_show_result(__("Sync Result"),
				__("Synced: {0} · Failed: {1} · Skipped: {2}", [m.synced, m.failed, m.skipped]),
				m.results);
			if (after) after();
		},
	});
}

// Render a per-record result table inside a dialog (errors shown in full).
function esui_show_result(title, summary, results) {
	const rows = (results || []).map((x) => {
		const icon = x.ok ? "✅" : "❌";
		const color = x.ok ? "#16a34a" : "#dc2626";
		return `<tr>
			<td style="white-space:nowrap">${frappe.utils.escape_html(x.employee || "")}</td>
			<td>${frappe.utils.escape_html(x.employee_name || "")}</td>
			<td style="color:${color}">${icon} ${frappe.utils.escape_html(x.message || "")}</td>
		</tr>`;
	}).join("");
	const html = `
		<div style="font-weight:600;margin-bottom:10px">${frappe.utils.escape_html(summary)}</div>
		<div style="max-height:60vh;overflow:auto">
		<table class="table table-bordered" style="font-size:13px">
			<thead><tr>
				<th>${__("Employee")}</th><th>${__("Name")}</th><th>${__("Result")}</th>
			</tr></thead>
			<tbody>${rows}</tbody>
		</table></div>`;
	const d = new frappe.ui.Dialog({ title, size: "large", fields: [{ fieldtype: "HTML", options: html }] });
	d.show();
}

// Dialog xuất Excel:
//   All Info      → file cũ (New Data import lại được + Old Data)
//   Info for Sign → danh sách in cho NV ký: field lấy theo ô "Info for Sign" của từng field trong
//                   Employee Self Update Info Setting (không chọn ở đây); luôn là thông tin mới nhất.
function _esui_excel_dialog(listview) {
	const API = "customize_erpnext.api.self_update_info.self_update_info_api";
	const selected = listview.get_checked_items().map((d) => d.name);
	frappe.xcall(`${API}.get_info_for_sign_fields`).then((labels) => {
		const esc = frappe.utils.escape_html;
		const scope = selected.length
			? __("{0} selected record(s)", [selected.length])
			: __("All records");
		const setting_link = `<a href="/app/employee-self-update-info-setting" target="_blank">${__("Employee Self Update Info Setting")}</a>`;
		const sign_info = labels.length
			? `<div class="text-muted small">${__("Information exported (ticked \"Info for Sign\" in {0}):", [setting_link])}</div>
				<ul style="margin:6px 0 0 18px">${labels.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`
			: `<div class="text-danger">${__("No field is ticked \"Info for Sign\" in {0}.", [setting_link])}</div>`;
		const d = new frappe.ui.Dialog({
			title: __("Download Excel"),
			fields: [
				{ fieldtype: "HTML", options: `<div class="text-muted" style="margin-bottom:6px">${scope}</div>` },
				{
					fieldtype: "Select",
					fieldname: "export_type",
					label: __("Export Type"),
					options: [
						{ value: "All Info", label: __("All Info") },
						{ value: "Info for Sign", label: __("Info for Sign") },
					],
					default: "All Info",
				},
				{
					fieldtype: "HTML",
					fieldname: "sign_fields",
					options: sign_info,
					depends_on: "eval:doc.export_type=='Info for Sign'",
				},
			],
			primary_action_label: __("Download"),
			primary_action(v) {
				const args = {
					names: selected.length ? JSON.stringify(selected) : "",
					export_type: v.export_type,
				};
				if (v.export_type === "Info for Sign" && !labels.length) {
					frappe.msgprint(__("No field is ticked \"Info for Sign\" in {0}.", [setting_link]));
					return;
				}
				d.hide();
				// download_excel trả file nhị phân → POST form để trình duyệt lưu (open_url_post kèm CSRF).
				open_url_post(`/api/method/${API}.download_excel`, args);
			},
		});
		d.show();
	});
}
