frappe.listview_settings['Uniform Rule'] = {
	onload(listview) {
		// See what every employee gets under the current rules (sizes from the Employee)
		listview.page.add_inner_button(__('Preview Assignments'), () =>
			frappe.set_route('query-report', 'Uniform Assignment Preview')
		);
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
				<li>Hai quy tắc <b>cùng điểm</b>: quy tắc có mã (UNI-RULE-…) lớn hơn thắng — nên tránh, thêm điều kiện để tách.</li>
			</ul>

			<p><b>Số lượng &amp; chu kỳ:</b></p>
			<ul style="padding-left:18px; margin:4px 0;">
				<li><b>First Issue Qty</b> — số cấp lần đầu. <b>Eligible After (Days)</b> — đủ điều kiện sau N ngày làm việc.</li>
				<li><b>Reissue Cycle (Months) / Reissue Qty</b> — chu kỳ &amp; số cấp bổ sung (<b>0 = không cấp bổ sung</b>).
					<i>Lưu quy tắc xong, hệ thống tự tính lại hạn cấp và Áo/Mũ của mọi hồ sơ (chạy nền, vài giây).</i></li>
				<li><b>One-Time Issue</b> — cấp 1 lần (mũ/dép/bình nước), không cấp bổ sung định kỳ; hỏng/mất thì thêm tay một dòng trên phiếu cấp phát (Damaged / Lost).</li>
			</ul>

			<p><b>Ngoại lệ từng người:</b> mở Hồ sơ đồng phục → tick <b>Manual Override</b> → chọn Áo/Mũ bằng tay. Bỏ tick = theo quy tắc.</p>
			<p class="text-muted">Gợi ý: bấm <b>Preview Assignments</b> để xem mỗi nhân viên sẽ nhận gì; <b>Active</b> để bật/tắt quy tắc mà không cần xoá.</p>
		</div>`);
	d.show();
}
