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

		// Nút Review/Sync phụ thuộc Setting "Disable Review".
		frappe.db.get_single_value("Employee Self Update Info Setting", "disable_review").then((dr) => {
			dr = cint(dr);

			if (!dr && frm.doc.status === "Submitted") {
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

			// Disable Review → sync từ Submitted; ngược lại chỉ khi Reviewed.
			const canSync = dr
				? ["Submitted", "Reviewed"].includes(frm.doc.status)
				: frm.doc.status === "Reviewed";
			if (canSync) {
				frm.add_custom_button(__("Sync to Employee"), () => _esui_form_sync_dialog(frm))
					.addClass("btn-primary");
			}
		});
	},
});

// Single-record sync dialog: pick fields (changed ones pre-checked).
function _esui_form_sync_dialog(frm) {
	frappe.call({
		method: "customize_erpnext.api.self_update_info.self_update_info_api.get_submission_view",
		args: { name: frm.doc.name },
		callback(r) {
			if (!r.message) return;
			const opts = [];
			(r.message.sections || []).forEach((sec) => {
				(sec.rows || []).forEach((row) => {
					if (row.custom) return; // custom fields không ghi vào Employee
					const val = row.value || "—";
					opts.push({
						label: `${frappe.utils.escape_html(row.label)} : ${frappe.utils.escape_html(val)}`,
						value: row.fieldname,
						checked: row.changed ? 1 : 0,
					});
				});
			});
			if (!opts.length) {
				frappe.msgprint(__("No syncable fields in this submission."));
				return;
			}
			const d = new frappe.ui.Dialog({
				title: __("Sync to Employee"),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						options: `<div class="text-muted" style="margin-bottom:6px">${__(
							"Changed fields are pre-selected. Adjust and confirm to write into the Employee record."
						)}</div>`,
					},
					{ fieldtype: "MultiCheck", fieldname: "fields", options: opts, columns: 1 },
				],
				primary_action_label: __("Sync"),
				primary_action() {
					const sel = d.get_value("fields") || [];
					if (!sel.length) {
						frappe.msgprint(__("Select at least one field."));
						return;
					}
					d.hide();
					frappe.call({
						method: "customize_erpnext.api.self_update_info.self_update_info_api.sync_to_employee",
						type: "POST",
						args: { names: JSON.stringify([frm.doc.name]), fields: JSON.stringify(sel) },
						freeze: true,
						freeze_message: __("Syncing to Employee..."),
						callback(res) {
							if (res.message) _esui_form_result(res.message);
							frm.reload_doc();
						},
					});
				},
			});
			// Toggle select all / none
			d.$wrapper.find(".modal-header").append(
				`<button class="btn btn-xs btn-default esui-toggle-all" style="margin:10px 0 0 15px">${__("Select all / none")}</button>`
			);
			d.$wrapper.find(".esui-toggle-all").on("click", () => {
				const boxes = d.$wrapper.find('[data-fieldname="fields"] input[type="checkbox"]');
				const anyOff = boxes.filter((i, el) => !el.checked).length > 0;
				boxes.prop("checked", anyOff).trigger("change");
			});
			d.show();
		},
	});
}

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
			let hasEditable = false;
			let html = `<style>
				.esui-sec{margin:0 0 14px}
				.esui-sec h5{margin:0 0 6px;color:#1e40af;font-weight:700}
				.esui-tbl{width:100%;border-collapse:collapse;font-size:13px}
				.esui-tbl td{border:1px solid #e3e8ef;padding:6px 10px;vertical-align:top}
				.esui-tbl td.l{width:38%;background:#f7f9fc;color:#475569;font-weight:600}
				.esui-chg{background:#fff7e6}
				.esui-old{color:#94a3b8;font-size:11px;margin-top:3px}
				.esui-badge{display:inline-block;font-size:10px;font-weight:700;color:#b45309;
					background:#fff7e6;border:1px solid #f0b429;border-radius:10px;padding:0 6px;margin-left:6px}
				.esui-edit{width:100%;font-size:13px;padding:3px 6px;border:1px solid #cbd5e1;border-radius:4px}
				.esui-edit:focus{border-color:#2563eb;outline:none}
			</style>`;
			(r.message.sections || []).forEach((sec) => {
				html += `<div class="esui-sec"><h5>${esc(sec.label)}</h5><table class="esui-tbl">`;
				sec.rows.forEach((row) => {
					const chg = row.changed && !synced;
					const oldHint = chg ? `<div class="esui-old">${__("Old")}: ${esc(row.old) || "—"}</div>` : "";
					const editable = row.editable && !synced;
					let cell;
					if (editable) {
						hasEditable = true;
						const v = esc(row.value);
						const fn = esc(row.fieldname);
						cell = row.multiline
							? `<textarea class="esui-edit" data-fieldname="${fn}" rows="2">${v}</textarea>`
							: `<input type="text" class="esui-edit" data-fieldname="${fn}" value="${v}">`;
						cell += oldHint;
					} else {
						const badge = chg ? `<span class="esui-badge">${__("changed")}</span>` : "";
						cell = `${esc(row.value) || "—"}${badge}${oldHint}`;
					}
					html += `<tr><td class="l">${esc(row.label)}</td><td class="${chg ? "esui-chg" : ""}">${cell}</td></tr>`;
				});
				html += `</table></div>`;
			});
			if (r.message.remarks) {
				html += `<div class="esui-sec"><h5>${__("Remarks")}</h5>
					<div style="border:1px solid #e3e8ef;border-radius:6px;padding:8px 10px;background:#fafafa">${esc(r.message.remarks)}</div></div>`;
			}
			wrap.$wrapper.html(html);

			// HR sửa trực tiếp field text → nút lưu lại data_json (khi chưa Synced).
			if (hasEditable) {
				// Bắt giá trị NGAY khi HR gõ (delegation) — tránh đọc nhầm input cũ
				// nếu data_view bị re-render giữa lúc gõ và lúc bấm Lưu.
				frm._esui_edits = {};
				wrap.$wrapper.off("input.esui change.esui").on("input.esui change.esui", ".esui-edit", function () {
					frm._esui_edits[this.dataset.fieldname] = this.value;
				});

				frm.add_custom_button(__("Save Field Edits"), () => {
					// Đọc DOM hiện tại + đè bằng giá trị bắt lúc gõ (chắc chắn đúng).
					const values = {};
					wrap.$wrapper.find(".esui-edit").each((i, el) => {
						if (el.dataset.fieldname) values[el.dataset.fieldname] = el.value;
					});
					Object.assign(values, frm._esui_edits || {});
					if (!Object.keys(values).length) {
						frappe.msgprint(__("No editable field found."));
						return;
					}
					frappe.call({
						method: "customize_erpnext.api.self_update_info.self_update_info_api.update_submission_values",
						type: "POST",
						args: { name: frm.doc.name, values: JSON.stringify(values) },
						freeze: true,
						freeze_message: __("Saving..."),
						callback(res) {
							if (res.message) {
								frappe.show_alert({
									message: __("Saved {0} field(s).", [res.message.changed]),
									indicator: res.message.changed ? "green" : "orange",
								});
							}
							frm.reload_doc();
						},
					});
				}).addClass("btn-primary");
			}
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
