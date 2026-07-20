// Copyright (c) 2026, TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Self Update Info Setting", {
	refresh(frm) {
		// Bypass code is for Administrator only — hide it from HR users.
		frm.toggle_display("bypass_code", frappe.session.user === "Administrator");

		frm.add_custom_button(__("Help"), () => show_setting_help());

		_render_self_update_qr(frm);
		frm.get_field("fields_intro").$wrapper.html(
			`<div class="text-muted small">${__(
				"Pick any Employee field (including custom fields) to let employees review and update it."
			)}</div>`
		);
		frm.get_field("new_join_intro").$wrapper.html(
			`<div class="text-muted small">${__(
				"A reusable preset of basic fields for new joiners. Click the button to copy this preset into Selected Fields above (replacing the current list)."
			)}</div>`
		);
	},

	btn_add_by_date(frm) {
		const run = () => frm.call("btn_add_by_date").then(() => frm.refresh());
		const noFilter = !frm.doc.filter_date && !frm.doc.group && !frm.doc.department && !frm.doc.custom_section;
		if (noFilter) {
			frappe.confirm(
				__("No filter selected — add ALL active employees?"),
				run
			);
		} else {
			run();
		}
	},

	btn_clear_all(frm) {
		frappe.confirm(__("Clear the whole employee list and filters?"), () => {
			frm.call("btn_clear_all").then(() => frm.refresh());
		});
	},

	btn_add_field(frm) {
		open_field_picker(frm);
	},

	btn_add_custom_field(frm) {
		open_custom_field_dialog(frm);
	},

	btn_apply_new_join_preset(frm) {
		const preset = frm.doc.selected_fields_for_new_join || [];
		if (!preset.length) {
			frappe.msgprint(__("The New-Join Preset is empty. Add fields to it first."));
			return;
		}
		frappe.confirm(
			__("Replace the current Selected Fields with the {0} field(s) from the New-Join Preset?", [preset.length]),
			() => {
				const COPY = [
					"employee_fieldname", "label_vi", "section_label", "widget",
					"required", "read_only", "enable", "is_custom", "custom_fieldtype", "custom_options",
				];
				frm.clear_table("selected_fields");
				preset.forEach((src) => {
					const row = frm.add_child("selected_fields");
					COPY.forEach((k) => (row[k] = src[k]));
				});
				frm.refresh_field("selected_fields");
				frm.dirty();
				frappe.show_alert({
					message: __("Copied {0} field(s) into Selected Fields. Save to apply.", [preset.length]),
					indicator: "green",
				});
			}
		);
	},
});

// Add a free-form field that does NOT exist on the Employee doctype.
function open_custom_field_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Add Custom Field"),
		fields: [
			{
				fieldname: "key",
				fieldtype: "Data",
				label: __("Key (storage id)"),
				reqd: 1,
				description: __("Letters, numbers and underscore only, e.g. tshirt_note"),
			},
			{
				fieldname: "label_vi",
				fieldtype: "Data",
				label: __("Label (Tiếng Việt)"),
				reqd: 1,
			},
			{ fieldname: "cb1", fieldtype: "Column Break" },
			{
				fieldname: "section_label",
				fieldtype: "Data",
				label: __("Section"),
				default: "General",
				reqd: 1,
			},
			{
				fieldname: "custom_fieldtype",
				fieldtype: "Select",
				label: __("Field Type"),
				options: ["Data", "Date", "Datetime", "Time", "Int", "Float", "Select", "Check", "Small Text", "Text", "Phone"],
				default: "Data",
			},
			{
				fieldname: "required",
				fieldtype: "Check",
				label: __("Required"),
			},
			{ fieldname: "sb", fieldtype: "Section Break" },
			{
				fieldname: "custom_options",
				fieldtype: "Small Text",
				label: __("Options (one per line)"),
				depends_on: "eval:doc.custom_fieldtype=='Select'",
			},
		],
		primary_action_label: __("Add"),
		primary_action(v) {
			const key = (v.key || "").trim().toLowerCase().replace(/[^a-z0-9_]/g, "_");
			if (!key) {
				frappe.msgprint(__("Enter a valid key."));
				return;
			}
			const exists = (frm.doc.selected_fields || []).some(
				(r) => r.employee_fieldname === key
			);
			if (exists) {
				frappe.msgprint(__("A field with key '{0}' already exists.", [key]));
				return;
			}
			frm.add_child("selected_fields", {
				employee_fieldname: key,
				label_vi: v.label_vi,
				section_label: v.section_label || "General",
				widget: "Auto",
				required: v.required ? 1 : 0,
				read_only: 0,
				is_custom: 1,
				custom_fieldtype: v.custom_fieldtype || "Data",
				custom_options: v.custom_options || "",
			});
			frm.refresh_field("selected_fields");
			frm.dirty();
			d.hide();
			frappe.show_alert({
				message: __("Custom field '{0}' added. Save to apply.", [key]),
				indicator: "green",
			});
		},
	});
	d.show();
}

// --- QR code + shareable link to the public self-update page ---
function _render_self_update_qr(frm) {
	const field = frm.get_field("info_html");
	if (!field) return;
	var url = window.location.origin + "/employee-self-update-info";
	url = url.replace("local", "com.vn");

	field.$wrapper.html(`
		<div style="display:flex;align-items:center;gap:20px;
			background:#ffffff;border:1px solid #bfdbfe;border-radius:10px;
			padding:14px 20px;margin-bottom:12px">
			<div id="self_update_info_qr_canvas" style="flex-shrink:0"></div>
			<div>
				<div style="font-weight:700;font-size:16px;color:#1e40af;margin-bottom:6px">
					📋 ${__("Employee self-update link")}
				</div>
				<div style="font-size:14px;color:#374151;word-break:break-all;margin-bottom:8px">
					<a href="${url}" target="_blank">${url}</a>
				</div>
				<div style="font-size:13px;color:#6b7280">
					${__("Share the QR code or link so employees can update their own information.")}
				</div>
			</div>
		</div>`);

	_load_qr_lib(() => {
		const el = document.getElementById("self_update_info_qr_canvas");
		if (!el || !window.QRCode) return;
		el.innerHTML = "";
		new QRCode(el, {
			text: url,
			width: 200,
			height: 200,
			colorDark: "#000000",
			colorLight: "#ffffff",
			correctLevel: QRCode.CorrectLevel.M,
		});
	});
}

function _load_qr_lib(cb) {
	if (window.QRCode) return cb();
	const s = document.createElement("script");
	s.src = "/assets/customize_erpnext/js/qrcode.min.js";
	s.onload = cb;
	s.onerror = () => {
		const s2 = document.createElement("script");
		s2.src = "https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js";
		s2.onload = cb;
		document.head.appendChild(s2);
	};
	document.head.appendChild(s);
}

function open_field_picker(frm) {
	frappe.model.with_doctype("Employee", () => {
		const meta = frappe.get_meta("Employee");
		const ALLOWED = [
			"Data", "Date", "Datetime", "Time", "Int", "Float", "Currency",
			"Select", "Check", "Small Text", "Text", "Long Text", "Link", "Phone",
		];
		const SKIP = new Set(
			(frm.doc.selected_fields || []).map((r) => r.employee_fieldname)
		);
		const options = (meta.fields || [])
			.filter((df) => ALLOWED.includes(df.fieldtype))
			.filter((df) => !df.hidden || df.fieldname.startsWith("custom_"))
			.filter((df) => !SKIP.has(df.fieldname))
			.map((df) => ({
				label: `${__(df.label || df.fieldname)} — ${df.fieldname} (${df.fieldtype})`,
				value: df.fieldname,
			}))
			.sort((a, b) => a.label.localeCompare(b.label));

		const d = new frappe.ui.Dialog({
			title: __("Add Employee Fields"),
			fields: [
				{
					fieldname: "section_label",
					fieldtype: "Data",
					label: __("Section (group label)"),
					default: "General",
					reqd: 1,
				},
				{
					fieldname: "fields",
					fieldtype: "MultiSelectPills",
					label: __("Employee Fields"),
					get_data() {
						return options;
					},
				},
			],
			primary_action_label: __("Add"),
			primary_action(values) {
				const picked = values.fields || [];
				if (!picked.length) {
					frappe.msgprint(__("Select at least one field."));
					return;
				}
				const by_name = {};
				(meta.fields || []).forEach((df) => (by_name[df.fieldname] = df));
				picked.forEach((fieldname) => {
					frm.add_child("selected_fields", {
						employee_fieldname: fieldname,
						// label_vi left blank → English default label is shown
						// until HR fills in a Vietnamese label.
						section_label: values.section_label || "General",
						widget: "Auto",
						required: 0,
						read_only: 0,
					});
				});
				frm.refresh_field("selected_fields");
				frm.dirty();
				d.hide();
				frappe.show_alert({
					message: __("Added {0} field(s). Save to apply.", [picked.length]),
					indicator: "green",
				});
			},
		});
		d.show();
	});
}

// Usage guide shown by the "Help" toolbar button.
function show_setting_help() {
	const html = `
<div style="font-size:13px;line-height:1.6">
  <p><b>Cấu hình trang nhân viên tự cập nhật thông tin</b> — <a href="/employee-self-update-info" target="_blank">/employee-self-update-info</a></p>

  <h5>1. Eligible Employees (nhân viên được phép)</h5>
  <ul>
    <li>Chọn bộ lọc <b>Date of Joining</b> / <b>Group</b> / <b>Department</b> / <b>Section</b> → bấm <b>Add Employees</b> để thêm NV Active khớp lọc (nhiều lọc = AND). <b>Không chọn lọc</b> → hỏi xác nhận rồi thêm <b>toàn bộ NV Active</b>.</li>
    <li><b>Clear All</b>: xoá danh sách + reset bộ lọc.</li>
    <li>Nhân viên chỉ tự khai được nếu có trong bảng này. <i>Riêng HR mở được bất kỳ nhân viên nào</i> (xem mục 5).</li>
  </ul>

  <h5>2. Verification (xác thực)</h5>
  <ul>
    <li><b>Validate by DOB</b>: NV phải nhập <b>2 chữ số ngày sinh</b> trước khi xem/gửi (chống spam, tránh sửa nhầm người). Gõ đủ 2 số đúng là vào thẳng, không cần bấm nút.</li>
    <li><b>Áp dụng cho MỌI người, kể cả HR/Admin</b> — không có ngoại lệ theo quyền.</li>
    <li><b>Bypass Code</b> (mã 2 chữ số, chỉ Administrator thấy): dùng thay ngày sinh. <b>HR dùng mã này để mở bất kỳ nhân viên nào</b> mà không cần biết ngày sinh từng người; cũng dùng khi ngày sinh trong hệ thống bị sai.</li>
  </ul>

  <h5>3. Fields shown to employees (Selected Fields) — <i>quyết định field hiển thị</i></h5>
  <ul>
    <li><b>+ Add Employee Field</b>: chọn field bất kỳ của Employee (kể cả custom field).</li>
    <li><b>+ Add Custom Field</b>: field tự do KHÔNG thuộc Employee (chỉ lưu trong bản khai, không sync).</li>
    <li>Các cột:
      <ul>
        <li><b>Label (Tiếng Việt)</b>: nhãn hiển thị; trống → dùng nhãn gốc của field.</li>
        <li><b>Detail</b>: ghi chú giải thích, hiện dưới nhãn (xuống dòng được; link tự bấm được).</li>
        <li><b>Placeholder</b>: chữ gợi ý mờ trong ô trống (VD "12 chữ số"). Không áp cho ô ngày / chọn / checkbox.</li>
        <li><b>Section</b>: các field cùng Section gom thành 1 nhóm trên trang.</li>
        <li><b>Widget</b>: <i>Auto</i> thông thường; <i>Address Province</i> / <i>Address Ward</i> cho địa chỉ (Tỉnh → Phường/Xã).</li>
        <li><b>Required</b> bắt buộc · <b>Read Only</b> chỉ xem · <b>Enable</b> tắt để ẩn field mà không xoá.</li>
        <li><b>Validation</b>: Digits / Phone / Email / CCCD (12 số) / CMND (9 số) / Past (ngày ≤ hôm nay) / Future (ngày ≥ hôm nay) / Regex; kèm Min–Max Length. Kiểm cả ở máy NV và ở server.</li>
      </ul>
    </li>
  </ul>

  <h5>4. New-Join Preset</h5>
  <ul>
    <li>Bảng field mẫu cho nhân viên mới. Nút <b>Fill Selected Fields from Preset</b> <b>thay thế</b> toàn bộ Selected Fields bằng preset (có hỏi xác nhận).</li>
  </ul>

  <h5>5. Duyệt &amp; đồng bộ về Employee (doctype <i>Employee Self Update Info</i>)</h5>
  <ul>
    <li>Trạng thái: <b>Draft → Submitted → Reviewed → Synced</b>. <b>Phải Review trước thì mới Sync được.</b></li>
    <li><b>List view</b>: chọn record → <b>Mark Reviewed</b>, <b>Sync to Employee</b> (chạy hàng loạt, hiện bảng kết quả từng NV kèm lỗi nếu có), <b>Download Excel</b>.</li>
    <li><b>Form view</b>: <b>Mark Reviewed</b> → <b>Sync to Employee</b>; nút <b>Edit in Portal</b> mở trang khai của chính NV đó để HR sửa hộ (HR nhập <b>Bypass Code</b> ở bước xác thực). HR sửa xong gửi lại → quay về <b>Submitted</b>, cần review lại.</li>
    <li>Khi Sync: <b>chỉ ghi các field thuộc Employee</b> (kể cả custom_); custom field tự do và Ghi chú <b>không</b> ghi vào Employee. Địa chỉ đầy đủ được dựng lại tự động.</li>
  </ul>

  <h5>6. Chia sẻ &amp; kết xuất</h5>
  <ul>
    <li><b>Mã QR + link</b> ở đầu form: gửi cho NV để tự khai.</li>
    <li><b>Download Excel</b>: chọn record → chỉ record đã chọn; không chọn → tất cả. File 2 sheet (New/Old) dùng import ngược vào Employee được.</li>
    <li>NV có thể <b>tải PDF</b> sau khi gửi. Trên trang, NV <b>quét mã QR trên CCCD</b> để tự điền số CCCD / ngày cấp / ngày hết hạn / số CMND cũ / ngày sinh — hoặc nhập tay.</li>
  </ul>

  <p style="color:#b45309"><b>Lưu ý:</b> mọi thay đổi trong Setting phải bấm <b>Save</b> mới có hiệu lực. Dữ liệu NV khai <b>không tự động</b> ghi vào Employee — chỉ ghi khi HR bấm <b>Sync to Employee</b> (sau khi Review).</p>
</div>`;
	const d = new frappe.ui.Dialog({
		title: __("Hướng dẫn sử dụng"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "guide", options: `<div style="max-height:70vh;overflow:auto;padding-right:6px">${html}</div>` }],
		primary_action_label: __("Đóng"),
		primary_action() { d.hide(); },
	});
	d.show();
}
