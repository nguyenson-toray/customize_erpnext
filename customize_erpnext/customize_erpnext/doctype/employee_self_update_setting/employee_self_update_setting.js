// Employee Self Update Setting — form client script

const SELF_UPDATE_URL = "https://erp.tiqn.com.vn:8888/employee-self-update";

frappe.ui.form.on('Employee Self Update Setting', {

	refresh(frm) {
		_render_self_update_qr(frm);
		_apply_config_field_access(frm);
	},

	btn_add_by_date(frm) {
		if (!frm.doc.filter_date && !frm.doc.group) {
			frappe.msgprint(__('Vui lòng chọn ít nhất một bộ lọc: Ngày nhận việc hoặc Group.'));
			return;
		}
		frm.call('btn_add_by_date').then(() => frm.refresh());
	},

	btn_clear_all(frm) {
		frappe.confirm(__('Xóa toàn bộ danh sách nhân viên và bộ lọc?'), () => {
			frm.call('btn_clear_all').then(() => frm.refresh());
		});
	},

	btn_reset_config(frm) {
		frappe.confirm(__('Reset field_config_json về mặc định?'), () => {
			frm.call('btn_reset_config').then(() => frm.refresh());
		});
	},

	before_save(frm) {
		// Validate and auto-format field_config_json
		const raw = (frm.doc.field_config_json || '').trim();
		if (!raw) return;
		try {
			const parsed = JSON.parse(raw);
			frm.set_value('field_config_json', JSON.stringify(parsed, null, 2));
		} catch (e) {
			frappe.msgprint({
				title: __('Lỗi định dạng JSON'),
				message: __('Field Config JSON không hợp lệ: {0}', [e.message]),
				indicator: 'red',
			});
			frappe.validated = false;
		}
	},
});

function _apply_config_field_access(frm) {
	const isAdmin = frappe.user.has_role('Administrator');
	const field = frm.get_field('field_config_json');
	const resetBtn = frm.get_field('btn_reset_config');
	if (!field) return;

	if (isAdmin) {
		field.df.read_only = 0;
		field.$wrapper.show();
		if (resetBtn) resetBtn.$wrapper.show();
	} else {
		field.df.read_only = 1;
		field.$wrapper.hide();
		if (resetBtn) resetBtn.$wrapper.hide();
	}
	frm.refresh_field('field_config_json');
}

function _render_self_update_qr(frm) {
	const field = frm.fields_dict['qr_info'];
	if (!field) return;

	field.$wrapper.html(`
		<div style="display:flex;align-items:center;gap:20px;
			background:#f0f7ff;border:1px solid #bfdbfe;border-radius:10px;
			padding:14px 20px;margin-bottom:12px">
			<div id="self_update_qr_canvas" style="flex-shrink:0"></div>
			<div>
				<div style="font-weight:700;font-size:14px;color:#1e40af;margin-bottom:6px">
					📋 Link cập nhật thông tin nhân viên
				</div>
				<div style="font-size:12px;color:#374151;word-break:break-all;margin-bottom:8px">
					<a href="${SELF_UPDATE_URL}" target="_blank">${SELF_UPDATE_URL}</a>
				</div>
				<div style="font-size:11px;color:#6b7280">
					Gửi mã QR hoặc link cho nhân viên để tự điền thông tin.
				</div>
			</div>
		</div>`);

	_load_qr_lib(() => {
		const el = document.getElementById('self_update_qr_canvas');
		if (!el || !window.QRCode) return;
		new QRCode(el, {
			text: SELF_UPDATE_URL,
			width: 200,
			height: 200,
			colorDark: '#000000',
			colorLight: '#f0f7ff',
			correctLevel: QRCode.CorrectLevel.M,
		});
	});
}

function _load_qr_lib(cb) {
	if (window.QRCode) return cb();
	const s = document.createElement('script');
	s.src = '/assets/customize_erpnext/js/qrcode.min.js';
	s.onload = cb;
	s.onerror = () => {
		const s2 = document.createElement('script');
		s2.src = 'https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js';
		s2.onload = cb;
		document.head.appendChild(s2);
	};
	document.head.appendChild(s);
}
