// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.query_reports["Maternity Tracking Report"] = {
	"filters": [
		{
			"fieldname": "detail",
			"label": __("Detail"),
			"fieldtype": "Check",
			"default": 0,
			"width": "80px"
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
			"options": "\nPregnant\nMaternity Leave\nYoung child",
			"width": "80px"
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"width": "80px"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"width": "80px"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nUpcoming\nActive\nCompleted",
			"width": "80px"
		},
		{
			"fieldname": "apply_pregnant_benefit",
			"label": __("Apply Pregnant Benefit"),
			"fieldtype": "Select",
			"options": "\nYes\nNo",
			"width": "80px"
		}
	],

	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Color coding for status
		if (column.fieldname == "status") {
			if (value == "Active") {
				value = `<span style="color: green; font-weight: bold;">${value}</span>`;
			} else if (value == "Upcoming") {
				value = `<span style="color: blue; font-weight: bold;">${value}</span>`;
			} else if (value == "Completed") {
				value = `<span style="color: gray;">${value}</span>`;
			}
		}

		// Color coding for maternity type - no icons, just colors
		if (column.fieldname == "type") {
			if (value == "Pregnant") {
				value = `<span style="color: #e91e63; font-weight: bold;">${value}</span>`;
			} else if (value == "Maternity Leave") {
				value = `<span style="color: #9c27b0; font-weight: bold;">${value}</span>`;
			} else if (value == "Young child") {
				value = `<span style="color: #ff9800; font-weight: bold;">${value}</span>`;
			}
		}

		return value;
	},

	onload: function(report) {
		// Add Summary Stats button
		report.page.add_inner_button(__("Summary Stats"), function() {
			show_summary_stats(report.data);
		});
	}
};

// Function to show summary statistics
function show_summary_stats(data) {
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
		completed: 0,
		with_benefit: 0,
		without_benefit: 0
	};

	data.forEach(row => {
		// Count by type
		if (row.type === "Pregnant") stats.pregnant++;
		if (row.type === "Maternity Leave") stats.maternity_leave++;
		if (row.type === "Young child") stats.young_child++;

		// Count by status
		if (row.status === "Active") stats.active++;
		if (row.status === "Upcoming") stats.upcoming++;
		if (row.status === "Completed") stats.completed++;

		// Count by benefit
		if (row.custom_apply_pregnant_benefit) stats.with_benefit++;
		else stats.without_benefit++;
	});

	let dialog = new frappe.ui.Dialog({
		title: __("Maternity Tracking Summary Statistics"),
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'summary_html',
				options: `
					<div class="row">
						<div class="col-md-6">
							<h5>📊 Overall Statistics</h5>
							<table class="table table-condensed">
								<tr><td><strong>Total Records:</strong></td><td>${stats.total_records}</td></tr>
							</table>
							
							<h5>🤰 By Maternity Type</h5>
							<table class="table table-condensed">
								<tr><td>🤰 Pregnant:</td><td>${stats.pregnant}</td></tr>
								<tr><td>🍼 Maternity Leave:</td><td>${stats.maternity_leave}</td></tr>
								<tr><td>👶 Young Child:</td><td>${stats.young_child}</td></tr>
							</table>
						</div>
						<div class="col-md-6">
							<h5>📅 By Status</h5>
							<table class="table table-condensed">
								<tr><td><span style="color: blue;">📅 Upcoming:</span></td><td>${stats.upcoming}</td></tr>
								<tr><td><span style="color: green;">🟢 Active:</span></td><td>${stats.active}</td></tr>
								<tr><td><span style="color: gray;">⚪ Completed:</span></td><td>${stats.completed}</td></tr>
							</table>
							
							<h5>💼 Benefit Application</h5>
							<table class="table table-condensed">
								<tr><td><span style="color: green;">✓ With Benefit:</span></td><td>${stats.with_benefit}</td></tr>
								<tr><td><span style="color: red;">✗ Without Benefit:</span></td><td>${stats.without_benefit}</td></tr>
							</table>
						</div>
					</div>
				`
			}
		]
	});
	
	dialog.show();
}