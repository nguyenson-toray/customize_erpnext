// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

const ONBOARDING_URL = "https://erp.tiqn.com.vn:8888/employee-onboarding";

frappe.ui.form.on("Employee Onboarding Settings", {
	refresh(frm) {

		// ── QR Code ───────────────────────────────────────────────────────────
		_render_onboarding_qr(frm);

		// Auto-add today's employees if list is empty
		if (!frm.doc.employees || frm.doc.employees.length === 0) {
			_load_by_date(frm, frappe.datetime.get_today(), true);
		}
	},

	btn_add_by_date(frm) {
		const date = frm.doc.filter_date;
		if (!date) {
			frappe.msgprint(__("Vui lòng chọn ngày gia nhập."));
			return;
		}
		_load_by_date(frm, date, false);
	},

	btn_clear_all(frm) {
		frappe.confirm(__("Xóa toàn bộ danh sách nhân viên?"), () => {
			frm.clear_table("employees");
			frm.refresh_field("employees");
		});
	}
});

function _render_onboarding_qr(frm) {
	const field = frm.fields_dict["qr_info"];
	if (!field) return;

	const wrapper = field.$wrapper;
	wrapper.html(`
		<div style="display:flex;align-items:center;gap:20px;
			background:#f0f7ff;border:1px solid #bfdbfe;border-radius:10px;
			padding:14px 20px;">
			<div id="onboarding_qr_canvas" style="flex-shrink:0"></div>
			<div>
				<div style="font-weight:700;font-size:14px;color:#1e40af;margin-bottom:6px">
					📋 Link điền thông tin nhân viên mới
				</div>
				<div style="font-size:12px;color:#374151;word-break:break-all;margin-bottom:8px">
					<a href="${ONBOARDING_URL}" target="_blank">${ONBOARDING_URL}</a>
				</div>
				<div style="font-size:11px;color:#6b7280">
					Gửi mã QR hoặc link cho nhân viên mới để tự điền thông tin.
				</div>
			</div>
		</div>`);

	_load_qr_lib(() => {
		const el = document.getElementById("onboarding_qr_canvas");
		if (!el || !window.QRCode) return;
		new QRCode(el, {
			text: ONBOARDING_URL,
			width: 120,
			height: 120,
			colorDark: "#1e40af",
			colorLight: "#f0f7ff",
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

function _load_by_date(frm, date, silent) {
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Employee",
			filters: { status: "Active", date_of_joining: date },
			fields: ["name", "employee_name"],
			limit: 500,
			order_by: "employee_name asc"
		},
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				if (!silent) {
					frappe.show_alert({
						message: __("Không có nhân viên nào gia nhập ngày {0}.", [frappe.datetime.str_to_user(date)]),
						indicator: "orange"
					});
				}
				return;
			}

			const existing_ids = new Set((frm.doc.employees || []).map(r => r.employee));
			let added = 0;
			rows.forEach(emp => {
				if (!existing_ids.has(emp.name)) {
					frm.add_child("employees", {
						employee: emp.name,
						employee_name: emp.employee_name
					});
					existing_ids.add(emp.name);
					added++;
				}
			});

			frm.refresh_field("employees");
			if (!silent) {
				if (added > 0) {
					frappe.show_alert({
						message: __("Đã thêm {0} nhân viên (ngày {1}).", [added, frappe.datetime.str_to_user(date)]),
						indicator: "green"
					});
				} else {
					frappe.show_alert({
						message: __("Tất cả nhân viên ngày {0} đã có trong danh sách.", [frappe.datetime.str_to_user(date)]),
						indicator: "blue"
					});
				}
			}
		}
	});
}
