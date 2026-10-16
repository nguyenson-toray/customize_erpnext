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

		// Cùng phiếu PDF như trang www (kèm cam kết + chữ ký), chỉ in field tick "Info for Sign" trong Setting.
		// Đang có ô sửa chưa lưu → PDF là bản đã lưu.
		frm.add_custom_button(__("Generate PDF"), () => {
			const API = "customize_erpnext.api.self_update_info.self_update_info_api";
			// Chưa tick field nào → báo ở đây: lỗi server qua open_url_post (form POST) đẩy trang sang JSON lỗi thô.
			frappe.xcall(`${API}.get_info_for_sign_fields`).then((labels) => {
				if (!labels.length) {
					frappe.msgprint(__("No field is ticked \"Info for Sign\" in {0}.", [
						`<a href="/app/employee-self-update-info-setting" target="_blank">${__("Employee Self Update Info Setting")}</a>`,
					]));
					return;
				}
				if (frm.is_dirty()) {
					frappe.show_alert({ message: __("Unsaved edits are not in the PDF. Save first."), indicator: "orange" });
				}
				// POST cùng trang: server trả attachment → trình duyệt tải file về, không mở tab trống.
				open_url_post(`/api/method/${API}.download_pdf_for_hr`, { name: frm.doc.name });
			});
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
					const val = row.display || row.value || "—";   // ngày: dd/mm/yyyy
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
			const tables = []; // bảng con (Học vấn, Quá trình làm việc) → bảng nhỏ sửa được
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
				.esui-sub{width:100%;border-collapse:collapse;font-size:12px;margin:0}
				.esui-sub th{background:#f7f9fc;color:#475569;font-weight:600;padding:3px 6px;border:1px solid #e3e8ef}
				.esui-sub td{padding:3px 4px;border:1px solid #e3e8ef}
				.esui-tedit{width:100%;font-size:12px;padding:2px 5px;border:1px solid #cbd5e1;border-radius:4px;background:#fff}
			</style>`;
			(r.message.sections || []).forEach((sec) => {
				html += `<div class="esui-sec"><h5>${esc(sec.label)}</h5><table class="esui-tbl">`;
				sec.rows.forEach((row) => {
					const chg = row.changed && !synced;
					const oldHint = chg ? `<div class="esui-old">${__("Old")}: ${esc(row.old_display || row.old) || "—"}</div>` : "";
					const editor = synced ? null : row.editor;
					const fn = esc(row.fieldname);
					const v = esc(row.value);
					let cell;
					if (row.columns) {
						// Bảng con: "Old" = dòng hiện có trên Employee (chữ nhiều dòng).
						const multi = (t) => esc(t || "").replace(/\n/g, "<br>");
						const old = chg ? `<div class="esui-old">${__("Old")}:<br>${multi(row.old_display) || "—"}</div>` : "";
						if (editor === "table") {
							cell = `<div class="esui-tblwrap" data-fieldname="${fn}"></div>`;
							tables.push(row);
						} else {
							const badge = chg ? `<span class="esui-badge">${__("changed")}</span>` : "";
							cell = `${multi(row.display) || "—"}${badge}`;
						}
						html += `<tr><td class="l">${esc(row.label)}</td><td class="${chg ? "esui-chg" : ""}">${cell}${old}</td></tr>`;
						return;
					}
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
						cell = `${esc(row.display || row.value) || "—"}${badge}`;   // ngày: dd/mm/yyyy
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
			tables.forEach((row) => _esui_make_table_editor(wrap, row, mark));
		},
	});
}

// Bảng con: bảng nhỏ sửa được (cột theo Setting), "+ Add Row" tới max_rows, ✕ xoá dòng.
// Giá trị = list dòng (giữ `name` dòng Employee để Sync sửa đúng dòng) → frm._esui_edits → data_json khi Save.
// Server làm sạch + kiểm lại ở validate_desk_edit (_clean_table_value, như trang www).
function _esui_make_table_editor(wrap, row, mark) {
	const box = wrap.$wrapper.find(`.esui-tblwrap[data-fieldname="${row.fieldname}"]`);
	const esc = frappe.utils.escape_html;
	// Phiếu chưa có field này (gửi trước khi bật) → bắt đầu từ dòng hiện có trên Employee, như trang www.
	const rows = (row.in_saved ? row.value || [] : row.old || []).map((r) => ({ ...r }));
	const cell = (c, i, v) => {
		const a = `class="esui-tedit" data-i="${i}" data-col="${esc(c.fieldname)}"`;
		if (c.fieldtype === "Select") {
			const opts = (c.options || []).map((o) =>
				`<option value="${esc(o)}"${String(v) === String(o) ? " selected" : ""}>${esc(o) || "&nbsp;"}</option>`).join("");
			return `<select ${a}>${opts}</select>`;
		}
		const type = c.fieldtype === "Date" ? "date" : (c.fieldtype === "Int" || c.fieldtype === "Float") ? "number" : "text";
		return `<input type="${type}" ${a} value="${esc(v == null ? "" : String(v))}">`;
	};
	// Cột ẩn ở dòng này (vd THCS/THPT → Trường, Ngành, Năm TN) — cùng luật _column_hidden ở server.
	const hidden = (c, r) => {
		const rule = row.required_if;
		const v = rule ? r[rule.column] : "";
		return !!rule && rule.columns.includes(c.fieldname) && !!v && !rule.values.includes(v);
	};
	const render = () => {
		// "*" = bắt buộc cố định; "(*)" = bắt buộc theo điều kiện (vd từ Trung cấp trở lên) — server kiểm khi Save.
		const rif = row.required_if;
		const mark_req = (c) => c.required ? " *" : (rif && (rif.required || []).includes(c.fieldname) ? " (*)" : "");
		const head = row.columns.map((c) => `<th>${esc(c.label)}${mark_req(c)}</th>`).join("") + "<th style='width:28px'></th>";
		const body = rows.map((r, i) => "<tr>" + row.columns.map((c) =>
			`<td>${hidden(c, r) ? "<span class='text-muted'>—</span>" : cell(c, i, r[c.fieldname])}</td>`).join("")
			+ `<td style="text-align:center"><a class="esui-tdel" data-i="${i}" title="${__("Delete")}" style="color:#dc2626;cursor:pointer">✕</a></td></tr>`).join("");
		const add = rows.length < (row.max_rows || 3)
			? `<button type="button" class="btn btn-xs btn-default esui-tadd" style="margin-top:4px">+ ${__("Add Row")}</button>`
			: `<div class="text-muted small" style="margin-top:4px">${__("At most {0} rows", [row.max_rows])}</div>`;
		box.html(`<table class="esui-sub"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${add}`);
	};
	const push = () => mark(row.fieldname, rows.map((r) => {
		const out = { ...r };
		row.columns.forEach((c) => { if (hidden(c, r)) out[c.fieldname] = ""; });
		return out;
	}));
	render();
	box.on("input change", ".esui-tedit", function () {
		const r = rows[+this.dataset.i];
		if (r) r[this.dataset.col] = this.value;
		// Đổi cột điều kiện (Trình độ) → vẽ lại để ẩn/hiện cột phụ thuộc.
		if (row.required_if && this.dataset.col === row.required_if.column && this.tagName === "SELECT") render();
		push();
	});
	box.on("click", ".esui-tdel", function () {
		rows.splice(+this.dataset.i, 1);
		render();
		push();
	});
	box.on("click", ".esui-tadd", () => {
		rows.push({});
		render();
		push();
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
