// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Self Update Info", {
	// Giá trị HR sửa trên bảng (data_view) được ghép vào data_json khi bấm Save / Ctrl+S.
	// Server kiểm tra lại ở controller validate (validate_desk_edit).
	before_save(frm) {
		const edits = frm._esui_edits || {};
		if (!Object.keys(edits).length) return;
		const saved = JSON.parse(frm.doc.data_json || "{}");
		Object.assign(saved, edits);
		frm.doc.data_json = JSON.stringify(saved);
	},

	after_save(frm) {
		frm._esui_edits = {};
	},

	refresh(frm) {
		if (frm.is_new()) return;

		_esui_render_view(frm);

		// Cùng phiếu PDF như trang www (kèm cam kết + chữ ký). Đang có ô sửa chưa lưu → PDF là bản đã lưu.
		frm.add_custom_button(__("Generate PDF"), () => {
			if (frm.is_dirty()) {
				frappe.show_alert({ message: __("Unsaved edits are not in the PDF. Save first."), indicator: "orange" });
			}
			window.open(
				"/api/method/customize_erpnext.api.self_update_info.self_update_info_api.download_pdf_for_hr?name="
					+ encodeURIComponent(frm.doc.name),
				"_blank"
			);
		});

		// "Edit in Portal" đã bỏ (06/10/2026): HR sửa trực tiếp trên bảng; CCCD nhập tay.

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
// HR sửa được ô text / select / tỉnh / xã (theo row.editor từ get_submission_view);
// sửa ô nào → form "Not Saved", lưu bằng nút Save chuẩn (before_save ghép vào data_json).
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
			const addr = [];   // ô tỉnh/xã cần dựng control Autocomplete sau khi chèn HTML
			const dates = [];  // ô ngày → control Date của Frappe
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
				.esui-edit{width:100%;font-size:13px;padding:3px 6px;border:1px solid #cbd5e1;border-radius:4px;background:#fff}
				.esui-edit:focus{border-color:#2563eb;outline:none}
				.esui-ac .form-group{margin-bottom:0}
			</style>`;
			(r.message.sections || []).forEach((sec) => {
				html += `<div class="esui-sec"><h5>${esc(sec.label)}</h5><table class="esui-tbl">`;
				sec.rows.forEach((row) => {
					const chg = row.changed && !synced;
					const oldHint = chg ? `<div class="esui-old">${__("Old")}: ${esc(row.old) || "—"}</div>` : "";
					const editor = synced ? null : row.editor;
					const fn = esc(row.fieldname);
					const v = esc(row.value);
					let cell;
					if (editor === "text") {
						cell = `<input type="text" class="esui-edit" data-fieldname="${fn}" value="${v}">`;
					} else if (editor === "textarea") {
						cell = `<textarea class="esui-edit" data-fieldname="${fn}" rows="2">${v}</textarea>`;
					} else if (editor === "select") {
						const opts = (row.options || []).map((o) =>
							`<option value="${esc(o)}"${o === row.value ? " selected" : ""}>${esc(__(o)) || "&nbsp;"}</option>`
						).join("");
						cell = `<select class="esui-edit" data-fieldname="${fn}">${opts}</select>`;
					} else if (editor === "province" || editor === "ward") {
						cell = `<div class="esui-ac" data-fieldname="${fn}"></div>`;
						addr.push(row);
					} else if (editor === "date") {
						cell = `<div class="esui-ac" data-fieldname="${fn}"></div>`;
						dates.push(row);
					} else {
						const badge = chg ? `<span class="esui-badge">${__("changed")}</span>` : "";
						cell = `${v || "—"}${badge}`;
					}
					cell += oldHint;
					html += `<tr><td class="l">${esc(row.label)}</td><td class="${chg ? "esui-chg" : ""}">${cell}</td></tr>`;
				});
				html += `</table></div>`;
			});
			if (r.message.remarks) {
				html += `<div class="esui-sec"><h5>${__("Remarks")}</h5>
					<div style="border:1px solid #e3e8ef;border-radius:6px;padding:8px 10px;background:#fafafa">${esc(r.message.remarks)}</div></div>`;
			}
			wrap.$wrapper.html(html);

			frm._esui_edits = {};
			const mark = (fieldname, value) => {
				frm._esui_edits[fieldname] = value;
				frm.dirty();
			};
			wrap.$wrapper.off("input.esui change.esui").on("input.esui change.esui", ".esui-edit", function () {
				mark(this.dataset.fieldname, this.value);
			});
			if (addr.length) _esui_make_address_controls(frm, wrap, addr, mark);
			if (dates.length) _esui_make_date_controls(wrap, dates, mark);
		},
	});
}

// Ngày: control Date của Frappe — hiện theo định dạng ngày hệ thống, get_value() trả ISO yyyy-mm-dd
// (đúng dạng data_json đang lưu). Server chuẩn hoá + kiểm tra Past/Future lại.
function _esui_make_date_controls(wrap, rows, mark) {
	rows.forEach((row) => {
		const parent = wrap.$wrapper.find(`.esui-ac[data-fieldname="${row.fieldname}"]`)[0];
		if (!parent) return;
		let ready = false;   // set_value lúc dựng không tính là HR sửa
		let current = row.value || "";
		const c = frappe.ui.form.make_control({
			parent,
			df: {
				fieldtype: "Date",
				fieldname: "esui_" + row.fieldname,
				onchange() {
					if (!ready) return;
					const v = c.get_value() || "";
					if (v === current) return;
					current = v;
					mark(row.fieldname, v);
				},
			},
			render_input: true,
			only_input: true,
		});
		Promise.resolve(c.set_value(row.value || "")).then(() => { ready = true; });
	});
}

// Tỉnh/xã: control Autocomplete thật của Frappe + helper public/js/vn_address_autocomplete.js
// (tìm không dấu, chỉ nhận giá trị trong danh sách). Đổi tỉnh → xoá xã + nạp list xã mới.
function _esui_make_address_controls(frm, wrap, rows, mark) {
	const addr = customize_erpnext.vn_address;
	const controls = {};
	const value_of = (fn) => (fn in frm._esui_edits ? frm._esui_edits[fn] : (rows.find((r) => r.fieldname === fn) || {}).value) || "";
	let ready = false;   // set_value lúc dựng control không tính là HR sửa

	const load_wards_for = (row) => {
		const c = controls[row.fieldname];
		const prov = row.province_field ? value_of(row.province_field) : "";
		return addr.load_wards(prov).then((wards) => {
			c.df.options = wards || [];
			c.set_data(wards || []);
		});
	};

	rows.forEach((row) => {
		const parent = wrap.$wrapper.find(`.esui-ac[data-fieldname="${row.fieldname}"]`)[0];
		if (!parent) return;
		const c = frappe.ui.form.make_control({
			parent,
			df: {
				fieldtype: "Autocomplete",
				fieldname: "esui_" + row.fieldname,
				options: [],
				placeholder: row.editor === "province" ? __("Select province") : __("Select ward"),
				onchange() {
					if (!ready) return;
					const val = c.get_value() || "";
					const data = c.get_data() || [];
					if (val && data.length && !data.some((d) => d.value === val)) {
						frappe.show_alert({ message: __("Please select a value from the list"), indicator: "orange" });
						c.set_value("");
						return;
					}
					if (val === value_of(row.fieldname)) return;
					mark(row.fieldname, val);
					if (row.editor === "province") {
						rows.filter((w) => w.province_field === row.fieldname).forEach((w) => {
							if (value_of(w.fieldname)) {
								mark(w.fieldname, "");
								controls[w.fieldname] && controls[w.fieldname].set_value("");
							}
							controls[w.fieldname] && load_wards_for(w);
						});
					}
				},
			},
			render_input: true,
			only_input: true,
		});
		addr.enhance_control(c);
		controls[row.fieldname] = c;
		c.set_value(row.value || "");
	});

	addr.load_provinces().then((provinces) => {
		rows.filter((r) => r.editor === "province").forEach((r) => {
			const c = controls[r.fieldname];
			if (!c) return;
			c.df.options = provinces;
			c.set_data(provinces);
		});
		return Promise.all(rows.filter((r) => r.editor === "ward" && controls[r.fieldname]).map(load_wards_for));
	}).then(() => { ready = true; });
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
