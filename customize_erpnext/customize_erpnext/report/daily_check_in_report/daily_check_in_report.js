frappe.query_reports["Daily Check-in Report"] = {
	"filters": [
		{
			"fieldname": "date",
			"label": __("Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "department",
			"label": __("Department"),
			"fieldtype": "Link",
			"options": "Department"
		},
		{
			"fieldname": "custom_group",
			"label": __("Group"),
			"fieldtype": "Link",
			"options": "Group"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "All\nPresent\nAbsent",
			"default": "All"
		},
		{
			"fieldname": "show_all_checkins",
			"label": __("Show All Check-ins"),
			"fieldtype": "Check",
			"default": 0,
			"description": __("Check to show all check-ins during the day, uncheck to show only first check-in")
		}
	],

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Tùy chỉnh màu sắc cho cột Status
		if (column.fieldname == "status") {
			if (data.status == "Present") {
				value = `<span style="color: green; font-weight: bold;">${value}</span>`;
			} else if (data.status == "Absent") {
				value = `<span style="color: red; font-weight: bold;">${value}</span>`;
			}
		}

		// Highlight multiple check-ins for same employee
		if (column.fieldname == "employee_code" && data.check_in_time) {
			// Kiểm tra xem có phải là check-in thứ 2, 3... của cùng nhân viên không
			let current_report = frappe.query_report;
			if (current_report && current_report.data) {
				let employee_checkins = current_report.data.filter(row =>
					row.employee_code === data.employee_code && row.check_in_time
				);
				if (employee_checkins.length > 1) {
					let checkin_index = employee_checkins.findIndex(row =>
						row.check_in_time === data.check_in_time
					);
					if (checkin_index > 0) {
						value = `<span style="color: #666; font-style: italic;">${value} (${checkin_index + 1})</span>`;
					}
				}
			}
		}

		return value;
	},

	"onload": function (report) {
		// Thêm hiển thị tổng hợp
		let total_absent = 0;
		let total_present = 0;
		let total_checkins = 0;

		// Cập nhật thông tin tổng hợp sau khi báo cáo render
		report.page.wrapper.on('render-complete', function () {
			let data = report.data;
			total_present = 0;
			total_absent = 0;
			total_checkins = 0;
			let unique_employees = new Set();

			if (data && data.length) {
				data.forEach(row => {
					if (row.check_in_time) {
						total_checkins++;
					}

					// Đếm unique employees
					unique_employees.add(row.employee_code);

					// Đếm present/absent cho unique employees
					if (!report.employee_status) {
						report.employee_status = {};
					}

					if (row.status === 'Present') {
						report.employee_status[row.employee_code] = 'Present';
					} else if (row.status === 'Absent' && !report.employee_status[row.employee_code]) {
						report.employee_status[row.employee_code] = 'Absent';
					}
				});

				// Đếm số nhân viên present và absent
				Object.values(report.employee_status || {}).forEach(status => {
					if (status === 'Present') {
						total_present++;
					} else if (status === 'Absent') {
						total_absent++;
					}
				});

				let total_employees = total_present + total_absent;
				let percentage = (total_employees > 0) ? ((total_present / total_employees) * 100).toFixed(2) : 0;

				// Tạo nội dung tổng hợp
				let show_all = report.get_filter_value('show_all_checkins');
				let summary_content = '';

				if (show_all) {
					summary_content = `
						<div style="font-weight: bold; font-size: 14px; margin-bottom: 10px;">Tổng hợp (Tất cả check-in):</div>
						<div>
							Tổng số check-in: <span style="font-weight: bold; color: blue;">${total_checkins}</span><br>
							Nhân viên có mặt: <span style="font-weight: bold; color: green;">${total_present}</span> / 
							Tổng số nhân viên: <span style="font-weight: bold;">${total_employees}</span> 
							(<span style="color: green;">${percentage}%</span> có mặt)
						</div>
					`;
				} else {
					summary_content = `
						<div style="font-weight: bold; font-size: 14px; margin-bottom: 10px;">Tổng hợp (Check-in đầu tiên):</div>
						<div>
							Nhân viên có mặt: <span style="font-weight: bold; color: green;">${total_present}</span> / 
							Tổng số nhân viên: <span style="font-weight: bold;">${total_employees}</span> 
							(<span style="color: green;">${percentage}%</span> có mặt)
						</div>
					`;
				}

				// Tạo hoặc cập nhật thông báo tổng hợp
				if (!report.summary_area) {
					report.summary_area = $(`
                        <div class="report-summary">
                            <div style="margin: 15px 0; padding: 10px; background-color: #f8f8f8; border-radius: 5px; border: 1px solid #e3e3e3;">
                                ${summary_content}
                            </div>
                        </div>
                    `);

					// Thêm vào đầu báo cáo
					report.page.wrapper.find('.report-wrapper').prepend(report.summary_area);
				} else {
					// Cập nhật nội dung
					report.summary_area.html(`
                        <div style="margin: 15px 0; padding: 10px; background-color: #f8f8f8; border-radius: 5px; border: 1px solid #e3e3e3;">
                            ${summary_content}
                        </div>
                    `);
				}
			}

			// Reset employee status for next render
			report.employee_status = {};
		});

		// Thêm button để export chi tiết
		// if (!report.export_btn) {
		// 	report.page.add_inner_button(__('Export Detailed'), function () {
		// 		let show_all = report.get_filter_value('show_all_checkins');
		// 		if (show_all) {
		// 			frappe.msgprint(__('Exporting detailed check-in report...'));
		// 			// Có thể thêm logic export custom ở đây
		// 		} else {
		// 			frappe.msgprint(__('Switch to "Show All Check-ins" mode for detailed export.'));
		// 		}
		// 	});
		// 	report.export_btn = true;
		// }
	}
};