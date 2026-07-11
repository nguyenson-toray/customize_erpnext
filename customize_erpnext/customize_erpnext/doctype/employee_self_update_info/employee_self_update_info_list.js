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
		listview.page.add_inner_button(__("Download Excel"), () => {
			const selected = listview.get_checked_items().map((d) => d.name);
			// download_excel streams a binary response; use a form POST so the
			// browser saves the file (open_url_post adds the CSRF token).
			open_url_post(
				"/api/method/customize_erpnext.api.self_update_info.self_update_info_api.download_excel",
				{ names: selected.length ? JSON.stringify(selected) : "" }
			);
		});

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

		listview.page.add_inner_button(__("Sync to Employee"), () => {
			const names = listview.get_checked_items().map((d) => d.name);
			if (!names.length) {
				frappe.msgprint(__("Select at least one record."));
				return;
			}
			frappe.confirm(
				__("Sync {0} record(s) into Employee? Only Reviewed records are applied.", [names.length]),
				() => esui_run_sync(names, () => listview.refresh())
			);
		});
	},
};

// Run sync and render the result dialog. Shared by list + form view.
function esui_run_sync(names, after) {
	frappe.call({
		method: "customize_erpnext.api.self_update_info.self_update_info_api.sync_to_employee",
		type: "POST",
		args: { names: JSON.stringify(names) },
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
