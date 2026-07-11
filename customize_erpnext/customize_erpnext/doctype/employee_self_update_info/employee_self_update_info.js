// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Self Update Info", {
	refresh(frm) {
		if (frm.is_new()) return;

		_esui_render_view(frm);

		if (frm.doc.status !== "Synced") {
			frm.add_custom_button(__("Edit in Portal"), () => {
				window.open("/employee-self-update-info?emp=" + encodeURIComponent(frm.doc.employee), "_blank");
			});
		}

		if (frm.doc.status === "Submitted") {
			frm.add_custom_button(__("Mark Reviewed"), () => {
				frappe.confirm(__("Mark this record as Reviewed?"), () => {
					frappe.call({
						method: "customize_erpnext.api.self_update_info.self_update_info_api.review_forms",
						type: "POST",
						args: { names: JSON.stringify([frm.doc.name]) },
						freeze: true,
						callback() { frm.reload_doc(); },
					});
				});
			}).addClass("btn-primary");
		}

		if (frm.doc.status === "Reviewed") {
			frm.add_custom_button(__("Sync to Employee"), () => {
				frappe.confirm(__("Sync this record into the Employee record?"), () => {
					frappe.call({
						method: "customize_erpnext.api.self_update_info.self_update_info_api.sync_to_employee",
						type: "POST",
						args: { names: JSON.stringify([frm.doc.name]) },
						freeze: true,
						freeze_message: __("Syncing to Employee..."),
						callback(r) {
							if (r.message) _esui_form_result(r.message);
							frm.reload_doc();
						},
					});
				});
			}).addClass("btn-primary");
		}
	},
});

// Render the submission as a readable table (label : value) in the data_view field.
function _esui_render_view(frm) {
	const wrap = frm.get_field("data_view");
	if (!wrap) return;
	frappe.call({
		method: "customize_erpnext.api.self_update_info.self_update_info_api.get_submission_view",
		args: { name: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			const esc = frappe.utils.escape_html;
			const synced = frm.doc.status === "Synced";
			let html = `<style>
				.esui-sec{margin:0 0 14px}
				.esui-sec h5{margin:0 0 6px;color:#1e40af;font-weight:700}
				.esui-tbl{width:100%;border-collapse:collapse;font-size:13px}
				.esui-tbl td{border:1px solid #e3e8ef;padding:6px 10px;vertical-align:top}
				.esui-tbl td.l{width:38%;background:#f7f9fc;color:#475569;font-weight:600}
				.esui-chg{background:#fff7e6}
				.esui-old{color:#94a3b8;font-size:11px}
				.esui-badge{display:inline-block;font-size:10px;font-weight:700;color:#b45309;
					background:#fff7e6;border:1px solid #f0b429;border-radius:10px;padding:0 6px;margin-left:6px}
			</style>`;
			(r.message.sections || []).forEach((sec) => {
				html += `<div class="esui-sec"><h5>${esc(sec.label)}</h5><table class="esui-tbl">`;
				sec.rows.forEach((row) => {
					const chg = row.changed && !synced;
					const oldHint = chg ? `<div class="esui-old">${__("Old")}: ${esc(row.old) || "—"}</div>` : "";
					const badge = chg ? `<span class="esui-badge">${__("changed")}</span>` : "";
					html += `<tr>
						<td class="l">${esc(row.label)}</td>
						<td class="${chg ? "esui-chg" : ""}">${esc(row.value) || "—"}${badge}${oldHint}</td>
					</tr>`;
				});
				html += `</table></div>`;
			});
			if (r.message.remarks) {
				html += `<div class="esui-sec"><h5>${__("Remarks")}</h5>
					<div style="border:1px solid #e3e8ef;border-radius:6px;padding:8px 10px;background:#fafafa">${esc(r.message.remarks)}</div></div>`;
			}
			wrap.$wrapper.html(html);
		},
	});
}

function _esui_form_result(m) {
	const x = (m.results || [])[0];
	if (!x) return;
	frappe.msgprint({
		title: x.ok ? __("Sync Result") : __("Sync Failed"),
		indicator: x.ok ? "green" : "red",
		message: `${x.ok ? "✅" : "❌"} ${frappe.utils.escape_html(x.message || "")}`,
	});
}
