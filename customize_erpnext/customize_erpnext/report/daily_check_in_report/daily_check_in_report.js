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

		return value;
	},

	"onload": function (report) {
		// Thêm CSS để điều chỉnh độ rộng cột STT - sử dụng selector chính xác hơn
		$("<style>")
			.prop("type", "text/css")
			.html(`
                /* Tăng độ rộng cột STT */
                .dt-scrollable .dt-cell.dt-cell--col-0, 
                .dt-scrollable .dt-cell--col-index {
                    min-width: 50px !important;
                    width: 50px !important;
                    max-width: 50px !important;
                   
                }
                .dt-cell.dt-cell--col-0.dt-cell--header.dt-cell--header-0, .dt-cell__content.dt-cell__content--col-0{
                    min-width: 50px !important;
                    width: 50px !important;
                    max-width: 50px !important;
                }
                
                /* Đảm bảo nội dung STT hiển thị đầy đủ */
                .dt-scrollable .dt-cell--col-0 .dt-cell__content,
                .dt-scrollable .dt-cell--col-index .dt-cell__content {
                    white-space: normal !important;
                    overflow: visible !important;
                    text-overflow: clip !important;
                }
            `)
			.appendTo("head");

		// Thêm hiển thị tổng hợp
		let total_absent = 0;
		let total_present = 0;

		// Cập nhật thông tin tổng hợp sau khi báo cáo render
		report.page.wrapper.on('render-complete', function () {
			let data = report.data;
			total_present = 0;
			total_absent = 0;

			if (data && data.length) {
				data.forEach(row => {
					if (row.status === 'Present') {
						total_present++;
					} else if (row.status === 'Absent') {
						total_absent++;
					}
				});

				let total = total_present + total_absent;
				let percentage = (total > 0) ? ((total_present / total) * 100).toFixed(2) : 0;

				// Tạo hoặc cập nhật thông báo tổng hợp
				if (!report.summary_area) {
					report.summary_area = $(`
                        <div class="report-summary">
                            <div style="margin: 15px 0; padding: 10px; background-color: #f8f8f8; border-radius: 5px; border: 1px solid #e3e3e3;">
                                <div style="font-weight: bold; font-size: 14px; margin-bottom: 10px;">Tổng hợp:</div>
                                <div>
                                    Số nhân viên có mặt: <span style="font-weight: bold; color: green;">${total_present}</span> / 
                                    Tổng số: <span style="font-weight: bold;">${total}</span> 
                                    (<span style="color: green;">${percentage}%</span> có mặt)
                                </div>
                            </div>
                        </div>
                    `);

					// Thêm vào đầu báo cáo
					report.page.wrapper.find('.report-wrapper').prepend(report.summary_area);
				} else {
					// Cập nhật nội dung
					report.summary_area.html(`
                        <div style="margin: 15px 0; padding: 10px; background-color: #f8f8f8; border-radius: 5px; border: 1px solid #e3e3e3;">
                            <div style="font-weight: bold; font-size: 14px; margin-bottom: 10px;">Tổng hợp:</div>
                            <div>
                                Số nhân viên có mặt: <span style="font-weight: bold; color: green;">${total_present}</span> / 
                                Tổng số: <span style="font-weight: bold;">${total}</span> 
                                (<span style="color: green;">${percentage}%</span> có mặt)
                            </div>
                        </div>
                    `);
				}
			}
		});
	}
};