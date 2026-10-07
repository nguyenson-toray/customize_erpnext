// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

// 1 màn hình theo khoảng ngày (viết lại 07/10/2026). Xem "hôm nay": From = To = hôm nay.
frappe.query_reports["Employee Maternity Report"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_start(),
			"reqd": 1,
			"width": "80px"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_end(),
			"reqd": 1,
			"width": "80px"
		},
		{
			// Bấm vào thẻ số phía trên cũng đặt filter này.
			// Giá trị phải khớp GROUPS trong employee_maternity_report.py.
			"fieldname": "show",
			"label": __("Maternity Status"),
			"fieldtype": "Select",
			"options": [
				// Để trống (không chọn) = tất cả; ô trống thì hiện tên bộ lọc làm placeholder.
				{ value: "", label: "" },
				{ value: "Pregnant", label: __("Pregnant") },
				{ value: "Maternity Leave", label: __("Maternity Leave") },
				{ value: "Young Child", label: __("Young Child") },
				{ value: "Returned to Work", label: __("Return to Work") },
				{ value: "Left", label: __("Left") },
			],
			"width": "80px"
		},
		{
			// Rút gọn = chỉ 4 mốc chu kỳ + ngày nghỉ việc. Bỏ tick = đủ cột ngày.
			"fieldname": "compact",
			"label": __("Compact View"),
			"fieldtype": "Check",
			"default": 0,
			"width": "40px"
		},
		{
			"fieldname": "department",
			"label": __("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": "80px"
		},
		{
			// Employee.custom_group là Link → Group. Data thì không có danh sách để chọn.
			"fieldname": "custom_group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group",
			"width": "80px"
		},
	],

	onload: function (report) {
		report.page.add_inner_button(__("Today"), function () {
			const today = frappe.datetime.get_today();
			report.set_filter_value({ from_date: today, to_date: today });
		});
		report.page.add_inner_button(__("Help"), show_maternity_report_help);
	},

	// Thẻ số bấm được → lọc theo nhóm; bấm lại thẻ đang chọn → bỏ lọc.
	after_refresh: function (report) {
		const groups = ["Pregnant", "Maternity Leave", "Young Child", "Returned to Work", "Left"];
		const current = report.get_filter_value("show");
		report.$summary.find(".summary-item").each(function (idx) {
			const group = groups[idx];
			if (!group) return;
			const active = current === group;
			$(this)
				.css({ cursor: "pointer", outline: active ? "2px solid var(--primary)" : "" })
				.attr("title", __("Click to show only this group"))
				.off("click.em_group")
				.on("click.em_group", () => report.set_filter_value("show", active ? "" : group));
		});
	}
};

// Nội dung hướng dẫn viết thẳng tiếng Việt — user yêu cầu 07/10/2026 (ngoại lệ của quy
// tắc English-first + vi.csv: đoạn văn dài, chỉ HR Việt Nam đọc). Sửa định nghĩa nhóm
// trong employee_maternity_report.py thì phải sửa cả đây.
function show_maternity_report_help() {
	const html = `
	<div class="em-help" style="line-height:1.6">
		<h5>Report này dùng để làm gì?</h5>
		<p>Theo dõi nhân viên nữ trong chu kỳ thai sản: <b>mang thai → nghỉ thai sản → đi làm lại (con nhỏ)</b>,
		và ai đã nghỉ việc trong chu kỳ đó. Mỗi dòng là <b>1 hồ sơ thai sản</b>.</p>

		<h5>Cách xem</h5>
		<ol>
			<li>Chọn <b>Từ ngày – Đến ngày</b> (mặc định là tháng hiện tại).</li>
			<li>Muốn biết <b>tình hình hôm nay</b> → bấm nút <b>Today</b> (Từ = Đến = hôm nay).</li>
			<li>Muốn chỉ xem <b>một nhóm</b>: bấm vào <b>thẻ số</b> của nhóm đó (VD thẻ <b>Đi làm lại</b>).
				Bấm lại thẻ đó để xem tất cả.</li>
			<li>Hoặc: ở ô lọc <b>Tình trạng thai sản</b>, chọn tên nhóm (VD <b>Đi làm lại</b>). Để trống ô này = xem tất cả.</li>
			<li>Lọc thêm theo <b>Department / Group</b> nếu cần.</li>
			<li><b>Rút gọn</b> (mặc định bật): chỉ hiện 4 mốc của chu kỳ — <b>Mang thai từ</b>, <b>Nghỉ thai sản từ</b>,
				<b>Ngày đi làm lại</b>, <b>Kết thúc chu kỳ</b> — và ngày nghỉ việc. Bỏ tick để xem đầy đủ:
				mỗi giai đoạn đủ 2 cột Từ – Đến (Mang thai, Nghỉ thai sản, Con nhỏ), thêm Bộ phận,
				Ngày nhận thông tin, Ngày dự sinh, Tuổi thai. Xuất Excel lấy đúng các cột đang hiện.</li>
		</ol>

		<h5>5 thẻ số nghĩa là gì? (đếm số NGƯỜI trong khoảng ngày đã chọn)</h5>
		<table class="table table-bordered table-condensed">
			<tr><td style="width:30%"><b>Mang thai</b></td><td>Có ít nhất 1 ngày đang mang thai trong kỳ.</td></tr>
			<tr><td><b>Nghỉ thai sản</b></td><td>Có ít nhất 1 ngày đang nghỉ thai sản trong kỳ.</td></tr>
			<tr><td><b>Con nhỏ</b></td><td>Đã đi làm lại, con chưa đủ 12 tháng, có ít nhất 1 ngày trong kỳ.
				Chưa nhập ngày sinh con thì chưa được tính vào nhóm này.</td></tr>
			<tr><td><b>Đi làm lại</b></td><td>Ngày đi làm lại (= ngày hết thai sản + 1) rơi vào kỳ và chưa nghỉ việc.
				Tính cả ngày trong <b>tương lai</b>: chọn kỳ là tháng sau để biết tháng sau có bao nhiêu người đi làm lại.</td></tr>
			<tr><td><b>Nghỉ việc</b></td><td>Trạng thái nhân viên là <b>Left</b> và ngày nghỉ việc rơi vào kỳ.</td></tr>
		</table>
		<p class="text-muted">Một người có thể nằm ở nhiều nhóm, ví dụ trong tháng vừa hết thai sản vừa đi làm lại.
		Từ ngày nghỉ việc trở đi, người đó không còn được tính là mang thai / nghỉ thai sản / con nhỏ.</p>

		<h5>Các cột cần lưu ý</h5>
		<table class="table table-bordered table-condensed">
			<tr><td style="width:30%"><b>Trong kỳ</b></td><td>Hồ sơ thuộc những nhóm nào trong kỳ đã chọn.</td></tr>
			<tr><td><b>Ngày đi làm lại</b></td><td>Ngày hết nghỉ thai sản + 1.</td></tr>
			<tr><td><b>Kết thúc chu kỳ</b></td><td>Ngày hết chế độ con nhỏ (con đủ 12 tháng). Để trống khi chưa nhập ngày sinh con.</td></tr>
			<tr><td><b>Số tháng nghỉ thai sản</b></td><td>Số tháng được nghỉ: mặc định 6; con thứ 2 được 7; sinh đôi cộng thêm 1 (con thứ 2 sinh đôi = 8).</td></tr>
			<tr><td><b>Nghỉ việc ở giai đoạn</b></td><td>
				Nhân viên nghỉ việc khi đang ở giai đoạn nào:
				<ul style="margin:4px 0 0 0">
					<li><b>Trước khi mang thai</b>: nghỉ trước ngày bắt đầu mang thai.</li>
					<li><b>Mang thai</b>: nghỉ khi đang mang thai.</li>
					<li><b>Nghỉ thai sản</b>: nghỉ khi đang nghỉ thai sản.</li>
					<li><b>Không quay lại làm</b>: nghỉ đúng ngày lẽ ra đi làm lại.</li>
					<li><b>Con nhỏ</b>: đã đi làm lại, nghỉ khi con chưa đủ 12 tháng.</li>
					<li><b>Sau chế độ con nhỏ</b>: nghỉ sau khi con đã đủ 12 tháng.</li>
				</ul>
				<div class="text-muted" style="margin-top:4px">Ví dụ: nghỉ thai sản 01/06 – 30/11, lẽ ra đi làm lại 01/12.
				Ngày nghỉ việc 01/12 → <b>Không quay lại làm</b>; ngày nghỉ việc 15/02 năm sau → <b>Con nhỏ</b>.</div>
			</td></tr>
		</table>

		<h5>Lưu ý</h5>
		<ul>
			<li>Ngày nghỉ việc là <b>ngày đầu tiên không còn đi làm</b> (ngày làm cuối = ngày nghỉ việc − 1).</li>
			<li>Số liệu lấy từ hồ sơ <b>Employee Maternity</b> — sai ngày trên hồ sơ thì report sai theo. Bấm vào mã hồ sơ ở cột đầu để mở và sửa.</li>
		</ul>
	</div>`;

	const d = new frappe.ui.Dialog({
		title: __("Help") + ": " + __("Employee Maternity Report"),
		size: "extra-large",
		fields: [{ fieldtype: "HTML", fieldname: "help_html", options: html }],
	});
	d.show();
}
