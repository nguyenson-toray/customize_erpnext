// Uniform Allocation — fetch eligible employees into the items table using the
// filter fields (uniform type, department, joining date range).
frappe.ui.form.on('Uniform Allocation', {
	setup(frm) {
		// Item filters driven by Uniform Setting → Uniform Item Group (no hardcoded group)
		frm.set_query('uniform_type_filter', () => {
			const filters = { variant_of: ['is', 'not set'] };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
		frm.set_query('item_code', 'items', () => {
			const filters = { has_variants: 0, disabled: 0 };
			if (frm._uniform_item_group) filters.item_group = frm._uniform_item_group;
			return { filters };
		});
	},
	onload(frm) {
		frappe.db
			.get_single_value('Uniform Setting', 'uniform_item_group')
			.then((v) => (frm._uniform_item_group = v));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Get Employees'), () => get_employees(frm));
		}
		frm.add_custom_button(__('Help'), () => show_help());
		toggle_reason_readonly(frm); // read-only only — must NOT dirty the form
	},
	allocation_type(frm) {
		apply_reason_rules(frm);
	},
});

// Issue Reason values allowed per Allocation Type (mirror of the server)
const ALLOWED_REASONS = {
	'New Issue': ['New Issue'],
	Supplement: ['Periodic Supplement'],
	Replacement: ['Damaged', 'Size Change'],
};

// Single fixed reason for the type, or '' for multi-reason (Replacement)
function reason_for_type(type) {
	const a = ALLOWED_REASONS[type] || [];
	return a.length === 1 ? a[0] : '';
}

// Reason editable only for Replacement; read-only (auto) for New Issue/Supplement.
// No value changes here → safe to call on refresh without dirtying the form.
function toggle_reason_readonly(frm) {
	if (!frm.fields_dict.items) return;
	const allowed = ALLOWED_REASONS[frm.doc.allocation_type] || [];
	const auto = reason_for_type(frm.doc.allocation_type);
	const grid = frm.fields_dict.items.grid;
	grid.update_docfield_property('issue_reason', 'read_only', auto ? 1 : 0);
	// Restrict the dropdown to reasons valid for the current Allocation Type
	grid.update_docfield_property('issue_reason', 'options', ['', ...allowed].join('\n'));
	grid.refresh();
}

// Called on Allocation Type change (a user action): set/clear reasons to match.
function apply_reason_rules(frm) {
	const type = frm.doc.allocation_type;
	const allowed = ALLOWED_REASONS[type] || [];
	const auto = reason_for_type(type);
	(frm.doc.items || []).forEach((r) => {
		if (auto) {
			if (r.issue_reason !== auto) frappe.model.set_value(r.doctype, r.name, 'issue_reason', auto);
		} else if (r.issue_reason && !allowed.includes(r.issue_reason)) {
			frappe.model.set_value(r.doctype, r.name, 'issue_reason', '');
		}
	});
	toggle_reason_readonly(frm);
}

function fill_available_qty(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code || !frm.doc.set_warehouse) return;
	frappe.db
		.get_value('Bin', { item_code: row.item_code, warehouse: frm.doc.set_warehouse }, 'actual_qty')
		.then((r) => {
			frappe.model.set_value(cdt, cdn, 'available_qty', (r.message && r.message.actual_qty) || 0);
		});
}

frappe.ui.form.on('Uniform Allocation Item', {
	item_code(frm, cdt, cdn) {
		fill_available_qty(frm, cdt, cdn);
		const reason = reason_for_type(frm.doc.allocation_type);
		if (reason) frappe.model.set_value(cdt, cdn, 'issue_reason', reason);
	},
	items_add(frm, cdt, cdn) {
		const reason = reason_for_type(frm.doc.allocation_type);
		if (reason) frappe.model.set_value(cdt, cdn, 'issue_reason', reason);
	},
});

function show_help() {
	const d = new frappe.ui.Dialog({
		title: __('Uniform Allocation — Hướng dẫn'),
		size: 'large',
	});
	d.$body.html(`
		<div style="font-size: var(--text-md); line-height:1.6;">
		<p><b>Cấp phát đồng phục theo lô — 1 chứng từ cho nhiều nhân viên.</b></p>
		<ol>
			<li><b>Chọn Loại cấp phát</b>:
				<ul>
					<li><b>New Issue (Cấp mới)</b>: NV chưa từng được cấp loại đó & đủ ngày làm việc.</li>
					<li><b>Supplement (Cấp bổ sung)</b>: NV <b>sắp đến hạn + quá hạn</b> (theo chu kỳ).</li>
					<li><b>Replacement (Thay thế)</b>: hỏng / đổi size / mất — chọn thủ công (bắt buộc đặt 1 bộ lọc).</li>
				</ul>
			</li>
			<li><b>Đặt bộ lọc</b> (tùy chọn): Loại đồng phục, Phòng ban, Nhóm, Giới tính, Ngày nhận việc.</li>
			<li><b>Bấm nút "Get Employees"</b> → tự đổ nhân viên đủ điều kiện vào bảng Items, kèm đúng variant theo size + số lượng.
				<br><span class="text-muted">NV thiếu Size áo/dép sẽ bị <b>bỏ qua</b> kèm cảnh báo — bổ sung hồ sơ rồi bấm lại.</span></li>
			<li><b>Kiểm tra / chỉnh</b> bảng Items nếu cần (thêm, xoá, đổi SL).</li>
			<li><b>Save → Submit</b>: tạo 1 phiếu xuất kho (Material Issue), trừ tồn, cập nhật hồ sơ + hạn cấp kế tiếp.
				<br><span class="text-muted">Bị chặn nếu: NV không Active / thiếu tồn kho / dòng không khớp Loại cấp phát.</span></li>
			<li><b>Hủy</b>: Cancel → hủy phiếu xuất, hoàn tồn kho, tính lại hồ sơ.</li>
		</ol>
		<p class="text-muted"><b>Mẹo:</b> "Supplement" + Get Employees = lấy toàn bộ NV sắp đến hạn & quá hạn cần cấp bổ sung.</p>
		</div>
	`);
	d.show();
}

function get_employees(frm) {
	if (!frm.doc.allocation_type) {
		frappe.msgprint(__('Select Allocation Type first.'));
		return;
	}
	const run = () =>
		frappe.call({
			method: 'customize_erpnext.uniform_control.api.uniform_api.get_eligible_employees',
			args: {
				allocation_type: frm.doc.allocation_type,
				uniform_type: frm.doc.uniform_type_filter || null,
				department: frm.doc.department_filter || null,
				group: frm.doc.group_filter || null,
				gender: frm.doc.gender_filter || null,
				joining_date_from: frm.doc.joining_date_from || null,
				joining_date_to: frm.doc.joining_date_to || null,
			},
			freeze: true,
			freeze_message: __('Fetching eligible employees...'),
			callback(r) {
				fill_items(frm, r.message || []);
			},
		});

	if ((frm.doc.items || []).length) {
		frappe.confirm(__('Replace the current items?'), run);
	} else {
		run();
	}
}

function fill_items(frm, rows) {
	const reason_map = { 'New Issue': 'New Issue', 'Supplement': 'Periodic Supplement' };
	const issue_reason = reason_map[frm.doc.allocation_type] || '';

	frm.clear_table('items');
	const skipped = [];
	rows.forEach((r) => {
		if (!r.item_code) {
			skipped.push(`${r.employee} — ${r.item_template}: ${r.item_error || ''}`);
			return;
		}
		const row = frm.add_child('items');
		row.employee = r.employee;
		row.employee_name = r.employee_name;
		row.department = r.department;
		row.item_code = r.item_code;
		row.qty = r.qty;
		row.available_qty = r.available_qty;
		row.issue_reason = issue_reason;
		row.shoe_rack_location = r.shoe_rack_location;
	});
	frm.refresh_field('items');

	if (!rows.length) {
		frappe.msgprint(__('No eligible employees found.'));
		return;
	}
	let msg = __('Added {0} row(s).', [frm.doc.items.length]);
	if (skipped.length) {
		msg +=
			'<br><br><b>' +
			__('Skipped {0} employee(s) — missing size or no variant (fill the profile, then retry):', [
				skipped.length,
			]) +
			'</b>';
		msg += '<br>' + skipped.map(frappe.utils.escape_html).join('<br>');
	}
	frappe.msgprint({ title: __('Get Employees'), message: msg, indicator: skipped.length ? 'orange' : 'green' });
}
