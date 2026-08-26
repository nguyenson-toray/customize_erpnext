// Copyright (c) 2026, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Maternity Report"] = {
	"filters": [
		{
			"fieldname": "as_on_date",
			"label": __("As On Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1,
			"width": "80px"
		},
		{
			"fieldname": "snapshot_only",
			"label": __("Only Active on As On Date"),
			"fieldtype": "Check",
			"default": 1,
			"width": "80px"
		},
		{
			"fieldname": "detail",
			"label": __("Detail"),
			"fieldtype": "Check",
			"default": 0,
			"width": "80px"
		},
		{
			// Mặc định Active + Inactive = "còn trong công ty". Người nghỉ thai sản mang
			// Employee.status = Inactive, nên bỏ Inactive ra là giấu đúng nhóm mà report
			// này sinh ra để theo dõi. Đây cũng là bộ status của
			// api/headcount.py::MATERNITY_EMPLOYEE_STATUSES, nhờ vậy report khớp với
			// number card "Maternity Leave" trên HR Overview.
			// Để trống = tất cả, kể cả người đã nghỉ việc.
			"fieldname": "employee_status",
			"label": __("Employee Status"),
			"fieldtype": "MultiSelectList",
			"default": ["Active", "Inactive"],
			"width": "100px",
			get_data: function (txt) {
				return ["Active", "Inactive", "Suspended", "Left"]
					.filter(v => !txt || v.toLowerCase().includes(txt.toLowerCase()))
					.map(v => ({ value: v, description: "" }));
			}
		},
		{
			"fieldname": "employee",
			"label": __("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": "80px"
		},
		{
			"fieldname": "employee_name",
			"label": __("Employee Name"),
			"fieldtype": "Data",
			"width": "80px"
		},
		{
			"fieldname": "department",
			"label": __("Department"),
			"fieldtype": "Link",
			"options": "Department",
			"width": "80px"
		},
		{
			"fieldname": "custom_section",
			"label": __("Section"),
			"fieldtype": "Data",
			"width": "80px"
		},
		{
			"fieldname": "custom_group",
			"label": __("Group"),
			"fieldtype": "Data",
			"width": "80px"
		},
		{
			"fieldname": "maternity_type",
			"label": __("Maternity Type"),
			"fieldtype": "Select",
			"options": "\nPregnant\nMaternity Leave\nYoung Child",
			"width": "80px"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nUpcoming\nActive\nCompleted",
			"width": "80px"
		},
	],

	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname == "status") {
			if (value == "Active") {
				value = `<span style="color: green; font-weight: bold;">${value}</span>`;
			} else if (value == "Upcoming") {
				value = `<span style="color: blue; font-weight: bold;">${value}</span>`;
			} else if (value == "Completed") {
				value = `<span style="color: gray;">${value}</span>`;
			}
		}

		if (column.fieldname == "type") {
			if (value == "Pregnant") {
				value = `<span style="color: #e91e63; font-weight: bold;">${value}</span>`;
			} else if (value == "Maternity Leave") {
				value = `<span style="color: #9c27b0; font-weight: bold;">${value}</span>`;
			} else if (value == "Young Child") {
				value = `<span style="color: #ff9800; font-weight: bold;">${value}</span>`;
			}
		}

		return value;
	},

	onload: function(report) {
		report.page.add_inner_button(__("Summary Stats"), function() {
			show_summary_stats(report.data, report.get_filter_value("as_on_date"));
		});
	}
};

function show_summary_stats(data, as_on_date) {
	if (!data || data.length === 0) {
		frappe.msgprint(__("No data available for summary"));
		return;
	}

	let stats = {
		total_records: data.length,
		pregnant: 0,
		maternity_leave: 0,
		young_child: 0,
		active: 0,
		upcoming: 0,
		completed: 0
	};

	data.forEach(row => {
		if (row.type === "Pregnant") stats.pregnant++;
		if (row.type === "Maternity Leave") stats.maternity_leave++;
		if (row.type === "Young Child") stats.young_child++;

		if (row.status === "Active") stats.active++;
		if (row.status === "Upcoming") stats.upcoming++;
		if (row.status === "Completed") stats.completed++;
	});

	let title = as_on_date
		? __("Maternity Summary as on {0}", [frappe.datetime.str_to_user(as_on_date)])
		: __("Employee Maternity Report Summary");

	let dialog = new frappe.ui.Dialog({
		title: title,
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'summary_html',
				options: `
					<div class="row">
						<div class="col-md-6">
							<h5>${__("Overall Statistics")}</h5>
							<table class="table table-condensed">
								<tr><td><strong>${__("Total Records")}:</strong></td><td>${stats.total_records}</td></tr>
							</table>

							<h5>${__("By Maternity Type")}</h5>
							<table class="table table-condensed">
								<tr><td>${__("Pregnant")}:</td><td>${stats.pregnant}</td></tr>
								<tr><td>${__("Maternity Leave")}:</td><td>${stats.maternity_leave}</td></tr>
								<tr><td>${__("Young Child")}:</td><td>${stats.young_child}</td></tr>
							</table>
						</div>
						<div class="col-md-6">
							<h5>${__("By Status")}</h5>
							<table class="table table-condensed">
								<tr><td><span style="color: blue;">${__("Upcoming")}:</span></td><td>${stats.upcoming}</td></tr>
								<tr><td><span style="color: green;">${__("Active")}:</span></td><td>${stats.active}</td></tr>
								<tr><td><span style="color: gray;">${__("Completed")}:</span></td><td>${stats.completed}</td></tr>
							</table>
						</div>
					</div>
				`
			}
		]
	});

	dialog.show();
}
