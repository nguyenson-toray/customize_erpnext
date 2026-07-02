frappe.listview_settings['Uniform Rule'] = {
	onload(listview) {
		// Apply the rules to every profile (fill Áo/Mũ được gán, keep manual ones)
		listview.page.add_inner_button(__('Apply Defaults to All'), () => {
			frappe.confirm(
				__('Apply default rules to all profiles without Manual Override?'),
				() => {
					frappe.call({
						method: 'customize_erpnext.uniform_control.api.uniform_api.apply_default_rules',
						freeze: true,
						freeze_message: __('Applying default rules...'),
						callback(r) {
							const m = r.message || {};
							frappe.msgprint(
								__('Updated {0} of {1} profiles.', [m.changed || 0, m.profiles || 0])
							);
						},
					});
				}
			);
		});
		listview.page.add_inner_button(__('Setup Guide'), () => show_rule_setup_guide());
	},
};

// Setup guide for Uniform Rules (IT Admin) — Vietnamese, easy to read.
function show_rule_setup_guide() {
	const d = new frappe.ui.Dialog({
		title: __('Uniform Rule — Hướng dẫn cài đặt'),
		size: 'extra-large',
		primary_action_label: __('Đã hiểu'),
		primary_action: () => d.hide(),
	});
	d.$body.html(`
		<div style="line-height:1.8; font-size:var(--text-md); padding:6px 8px;">
			<p><b>Uniform Rule là gì?</b><br>
			Mỗi quy tắc trả lời: <b>AI</b> (điều kiện) được cấp <b>MÓN GÌ</b> (Item), <b>MẤY CÁI</b> (First Issue Qty),
			và <b>CHU KỲ</b> cấp lại. Mỗi <b>Category</b> (Shirt/Cap/Shoe/Bottle) chỉ cấp <b>1 món/người</b> —
			quy tắc <b>cụ thể hơn thắng</b> quy tắc chung.</p>

			<p><b>Điền Item theo Category:</b></p>
			<ul style="padding-left:18px; margin:4px 0;">
				<li><b>Shirt / Shoe</b> → chọn <b>template</b> (item có biến thể, vd "Áo sơ mi nam", "Dép"). Hệ thống tự chọn size theo hồ sơ.</li>
				<li><b>Cap</b> → chọn <b>biến thể mũ cụ thể</b> (theo màu/vai trò, vd "Mũ Đỏ - Qc").</li>
				<li><b>Bottle</b> → item đơn (vd "Bình nước").</li>
			</ul>

			<p><b>Điều kiện AI (để trống = áp dụng tất cả):</b></p>
			<ul style="padding-left:18px; margin:4px 0;">
				<li><b>Grades / Designations</b> — <b>chọn nhiều</b> (popup). Nhân viên khớp nếu Cấp bậc / Chức danh
					<b>nằm trong</b> danh sách. Vd 1 quy tắc áo sơ mi chọn cả Staff/Leader/Sub Leader/Manager/Factory Manager
					thay vì tạo 5 quy tắc.</li>
				<li><b>Group / Section / Gender</b> — chọn đơn. Group = tổ (custom_group); Section = bộ phận (custom_section).</li>
			</ul>

			<p><b>Khi nhân viên khớp nhiều quy tắc (cùng Category) — quy tắc nào thắng?</b><br>
			Mỗi điều kiện khớp cộng "điểm cụ thể", quy tắc <b>tổng điểm cao nhất thắng</b>:</p>
			<table class="table table-sm table-bordered" style="max-width:320px; margin:4px 0;">
				<thead><tr><th>Điều kiện</th><th class="text-right">Điểm</th></tr></thead>
				<tbody>
					<tr><td>Designations</td><td class="text-right">16</td></tr>
					<tr><td>Grades</td><td class="text-right">8</td></tr>
					<tr><td>Group</td><td class="text-right">4</td></tr>
					<tr><td>Section</td><td class="text-right">2</td></tr>
					<tr><td>Gender</td><td class="text-right">1</td></tr>
				</tbody>
			</table>
			<ul style="padding-left:18px; margin:4px 0;">
				<li><b>Designation nặng nhất (16)</b> — luôn thắng các tầng tổ chức khác.</li>
				<li><b>Grade (8) &gt; Group (4) &gt; Section (2)</b>: vai trò quan trọng hơn tổ/bộ phận →
					<b>Tổ trưởng (Leader) luôn đội mũ Leader</b> dù ở QC hay bộ phận nào.</li>
				<li><b>Priority</b> chỉ phá hoà khi 2 quy tắc <b>cùng điểm</b> — không đè được quy tắc cụ thể hơn.</li>
			</ul>

			<p><b>Số lượng &amp; chu kỳ:</b></p>
			<ul style="padding-left:18px; margin:4px 0;">
				<li><b>First Issue Qty</b> — số cấp lần đầu. <b>Eligible After (Days)</b> — đủ điều kiện sau N ngày làm việc.</li>
				<li><b>Reissue Cycle (Months) / Reissue Qty</b> — chu kỳ &amp; số cấp bổ sung (<b>0 = không cấp bổ sung</b>).
					<i>Đổi chu kỳ xong → chạy "Recompute Due Dates" ở danh sách Employee Uniform Profile.</i></li>
				<li><b>One-Time Issue</b> — cấp 1 lần (mũ/dép/bình nước), không cấp bổ sung định kỳ; cấp lại qua Replacement.</li>
			</ul>

			<p class="text-muted">Gợi ý: dùng cột <b>Category</b> ở đầu danh sách để lọc nhanh; <b>Active</b> để bật/tắt quy tắc mà không cần xoá.</p>
		</div>`);
	d.show();
}
