// Uniform Allocation — one kind of allocation. "Get Employees" adds every item that
// is due (first issue for new employees, periodic re-issue up to "Due On or
// Before"), each row with its own Issue Reason. Rows added by hand pick Damaged /
// Lost / Size Change.
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
		frm.clear_custom_buttons();
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Get Employees'), () => get_employees(frm));
		}
		frm.add_custom_button(__('Help'), () => show_help());

		// Opened from the dashboard's "Create Allocation for Due" button
		if (frm.is_new() && frappe.flags.uniform_auto_get) {
			frappe.flags.uniform_auto_get = false;
			get_employees(frm);
		}
	},
});

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
	},
});

function show_help() {
	const d = new frappe.ui.Dialog({
		title: __('Uniform Allocation — Hướng dẫn'),
		size: 'large',
	});
	d.$body.html(`
		<div style="font-size: var(--text-md); line-height:1.6;">
		<p><b>Một phiếu cấp phát cho nhiều nhân viên.</b></p>
		<ol>
			<li><b>Get Employees</b>: hệ thống tự thêm mọi món đến hạn, mỗi dòng ghi sẵn lý do:
				<ul>
					<li><b>New Issue</b>: nhân viên chưa từng nhận loại đó (thường là người mới, đủ số ngày làm việc theo quy tắc).</li>
					<li><b>Periodic Supplement</b>: đến hạn cấp lại trước ngày <b>Due On or Before</b> (để trống = hôm nay + số ngày nhắc trước).</li>
				</ul>
				Có thể lọc theo Bộ phận / Tổ / Loại đồng phục, hoặc chỉ lấy một loại lý do (ô <b>Include</b>). Bấm nhiều lần để gộp, dòng trùng tự bỏ qua.
			</li>
			<li><b>Thêm tay</b> một dòng khi đồ bị hỏng, mất hoặc đổi size: chọn nhân viên, món, lý do <b>Damaged / Lost / Size Change</b>.</li>
			<li>Tick <b>Reuse Old Item</b> nếu cấp lại đồ cũ thu hồi được (không trừ kho).</li>
			<li><b>Save → Submit</b>: tạo phiếu xuất kho, trừ tồn, cập nhật lịch sử cấp và hạn cấp lại của từng người.
				<br><span class="text-muted">Bị chặn nếu: nhân viên đã nghỉ, thiếu tồn kho, hoặc dòng chưa có lý do.</span></li>
			<li><b>Cancel</b>: hủy phiếu xuất kho, hoàn tồn, khôi phục lịch sử cấp.</li>
		</ol>
		<p class="text-muted">Size áo/dép lấy từ hồ sơ Employee; chưa khai size dép thì cấp Free Size.</p>
		</div>
	`);
	d.show();
}

function get_employees(frm) {
	frappe.call({
		method: 'customize_erpnext.uniform_control.api.uniform_api.get_due_rows',
		args: {
			uniform_type: frm.doc.uniform_type_filter || null,
			department: frm.doc.department_filter || null,
			group: frm.doc.group_filter || null,
			due_before: frm.doc.due_before || null,
			issue_filter: frm.doc.issue_filter || 'All',
		},
		freeze: true,
		freeze_message: __('Fetching employees due...'),
		callback(r) {
			fill_items(frm, r.message || []);
		},
	});
}

// Append (accumulate) to the items list across Get Employees runs; skip rows
// already present (same employee + item) and rows without a resolvable item.
function fill_items(frm, rows) {
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
		row.issue_reason = r.issue_reason;
		row.shoe_rack_location = r.shoe_rack_location;
		added++;
	});
	frm.refresh_field('items');
	if (added) frm.dirty();

	let msg = __('Added {0} row(s); total {1}.', [added, (frm.doc.items || []).length]);
	if (dup) msg += '<br>' + __('Skipped {0} already in the list.', [dup]);
	if (skipped.length) {
		msg +=
			'<br><br><b>' +
			__('Skipped {0} item(s) — no size or no matching variant (fix the Employee or the item, then retry):', [
				skipped.length,
			]) +
			'</b><br>' +
			skipped.map(frappe.utils.escape_html).join('<br>');
	}
	frappe.msgprint({ title: __('Get Employees'), message: msg, indicator: skipped.length ? 'orange' : 'green' });
}
