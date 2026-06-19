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
		setup_buttons(frm);
		toggle_reason_readonly(frm); // read-only only — must NOT dirty the form
		toggle_filters(frm);
	},
	allocation_type(frm) {
		setup_buttons(frm);
		apply_reason_rules(frm);
		toggle_filters(frm);
	},
});

// Get Employees only for New Issue / Supplement (Replacement = manual per person).
function setup_buttons(frm) {
	frm.clear_custom_buttons();
	if (frm.doc.docstatus === 0 && frm.doc.allocation_type !== 'Replacement') {
		frm.add_custom_button(__('Get Employees'), () => get_employees(frm));
	}
	frm.add_custom_button(__('Help'), () => show_help());
}

// Filters shown per Allocation Type:
//  - New Issue : type/dept/group/gender + joining date
//  - Supplement: type/dept/group/gender + due date / overdue (no joining date)
//  - Replacement: none (HR adds each person manually)
const FILTERS_BY_TYPE = {
	'New Issue': ['uniform_type_filter', 'department_filter', 'group_filter', 'gender_filter',
		'joining_date_from', 'joining_date_to'],
	Supplement: ['uniform_type_filter', 'department_filter', 'group_filter', 'gender_filter',
		'due_date_from', 'due_date_to', 'overdue_only'],
	Replacement: [],
};
const ALL_FILTERS = ['uniform_type_filter', 'department_filter', 'group_filter', 'gender_filter',
	'joining_date_from', 'joining_date_to', 'due_date_from', 'due_date_to', 'overdue_only'];

function toggle_filters(frm) {
	const visible = FILTERS_BY_TYPE[frm.doc.allocation_type] || [];
	ALL_FILTERS.forEach((f) => frm.set_df_property(f, 'hidden', visible.includes(f) ? 0 : 1));
	// Replacement: hide the whole filter section
	frm.set_df_property('section_filters', 'hidden', frm.doc.allocation_type === 'Replacement' ? 1 : 0);
}

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
					<li><b>Replacement (Thay thế)</b>: hỏng / đổi size / mất — HR <b>thêm từng người thủ công</b> (không lọc, không Get Employees).</li>
				</ul>
			</li>
			<li><b>Đặt bộ lọc</b> (tùy chọn): Loại đồng phục, Phòng ban, Nhóm, Giới tính, Ngày nhận việc; riêng <b>Hạn cấp từ/đến</b> &amp; <b>Chỉ quá hạn</b> chỉ hiện khi loại = Supplement.</li>
			<li><b>Bấm nút "Get Employees"</b> → <b>cộng dồn</b> nhân viên đủ điều kiện vào bảng Items (bấm nhiều lần với bộ lọc khác nhau để gộp; dòng trùng tự bỏ qua).
				<br><span class="text-muted">NV thiếu Size áo/dép sẽ bị <b>bỏ qua</b> kèm cảnh báo — bổ sung hồ sơ rồi bấm lại.</span></li>
			<li><b>Kiểm tra / chỉnh</b> bảng Items nếu cần (thêm, xoá, đổi SL). Lưu sẽ tự <b>loại dòng trùng</b> (cùng NV + item).</li>
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
			due_date_from: frm.doc.due_date_from || null,
			due_date_to: frm.doc.due_date_to || null,
			overdue_only: frm.doc.overdue_only ? 1 : 0,
		},
		freeze: true,
		freeze_message: __('Fetching eligible employees...'),
		callback(r) {
			fill_items(frm, r.message || []);
		},
	});
}

// Append (accumulate) to the items list across Get Employees runs; skip rows
// already present (same employee + item) and rows without a resolvable item.
function fill_items(frm, rows) {
	const reason_map = { 'New Issue': 'New Issue', 'Supplement': 'Periodic Supplement' };
	const issue_reason = reason_map[frm.doc.allocation_type] || '';

	const seen = new Set((frm.doc.items || []).map((r) => `${r.employee}|${r.item_code}`));
	const skipped = [];
	let added = 0;
	let dup = 0;
	rows.forEach((r) => {
		if (!r.item_code) {
			skipped.push(`${r.employee} — ${r.item_template}: ${r.item_error || ''}`);
			return;
		}
		const key = `${r.employee}|${r.item_code}`;
		if (seen.has(key)) {
			dup++;
			return;
		}
		seen.add(key);
		const row = frm.add_child('items');
		row.employee = r.employee;
		row.employee_name = r.employee_name;
		row.department = r.department;
		row.item_code = r.item_code;
		row.qty = r.qty;
		row.available_qty = r.available_qty;
		row.issue_reason = issue_reason;
		row.shoe_rack_location = r.shoe_rack_location;
		added++;
	});
	frm.refresh_field('items');

	let msg = __('Added {0} row(s); total {1}.', [added, (frm.doc.items || []).length]);
	if (dup) msg += '<br>' + __('Skipped {0} already in the list.', [dup]);
	if (skipped.length) {
		msg +=
			'<br><br><b>' +
			__('Skipped {0} employee(s) — missing size or no variant (fill the profile, then retry):', [
				skipped.length,
			]) +
			'</b><br>' +
			skipped.map(frappe.utils.escape_html).join('<br>');
	}
	frappe.msgprint({ title: __('Get Employees'), message: msg, indicator: skipped.length ? 'orange' : 'green' });
}
