// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// Global variable to store current chart type
window.daily_timesheet_chart_type = "Department Summary";

frappe.query_reports["Daily Timesheet Report"] = {
	"filters": [
		{
			"fieldname": "date_type",
			"label": __("Date Type"),
			"fieldtype": "Select",
			"options": "Single Date\nDate Range\nMonthly",
			"default": "Date Range",
			"reqd": 1
		},
		{
			"fieldname": "single_date",
			"label": __("Date"),
			"fieldtype": "Date",
			"depends_on": "eval:doc.date_type=='Single Date'",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"depends_on": "eval:doc.date_type=='Date Range'",
			"default": frappe.datetime.month_start()
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"depends_on": "eval:doc.date_type=='Date Range'",
			"default": frappe.datetime.get_today()
		},
		{
			"fieldname": "month",
			"label": __("Month"),
			"fieldtype": "Select",
			"options": "\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12",
			"depends_on": "eval:doc.date_type=='Monthly'",
			"default": new Date().getMonth() + 1
		},
		{
			"fieldname": "year",
			"label": __("Year"),
			"fieldtype": "Int",
			"depends_on": "eval:doc.date_type=='Monthly'",
			"default": new Date().getFullYear()
		},
		{
			"fieldname": "department",
			"label": __("Department"),
			"fieldtype": "MultiSelectList",
			"options": "Department",
			"get_data": function (txt) {
				return frappe.db.get_link_options('Department', txt);
			}
		},
		{
			"fieldname": "custom_section",
			"label": __("Section"),
			"fieldtype": "MultiSelectList",
			"get_data": function (txt) {
				return frappe.db.get_list('Employee', {
					fields: ['custom_section'],
					filters: {
						'custom_section': ['like', '%' + txt + '%']
					},
					group_by: 'custom_section'
				}).then(function (data) {
					return data.map(function (item) {
						return {
							value: item.custom_section,
							label: item.custom_section
						};
					});
				});
			}
		},
		{
			"fieldname": "custom_group",
			"label": __("Group"),
			"fieldtype": "MultiSelectList",
			"get_data": function (txt) {
				return frappe.db.get_list('Employee', {
					fields: ['custom_group'],
					filters: {
						'custom_group': ['like', '%' + txt + '%']
					},
					group_by: 'custom_group'
				}).then(function (data) {
					return data.map(function (item) {
						return {
							value: item.custom_group,
							label: item.custom_group
						};
					});
				});
			}
		},
		{
			"fieldname": "employee",
			"label": __("Employee"),
			"fieldtype": "Link",
			"options": "Employee"
		},
		{
			"fieldname": "status",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nPresent\nAbsent\nHalf Day\nWork From Home\nOn Leave\nSunday"
		},
		{
			"fieldname": "summary",
			"label": __("Summary"),
			"fieldtype": "Check",
			"default": 0,
			"description": __("Group by employee and sum totals for date range")
		},
		{
			"fieldname": "detail_columns",
			"label": __("Detail Columns"),
			"fieldtype": "Check",
			"default": 0,
			"description": __("Show detailed columns (Shift Determined By, Morning/Afternoon Hours, Total Hours, Late Entry, Early Exit, Maternity Benefit)")
		},
		{
			"fieldname": "show_zero",
			"label": __("Show Zero"),
			"fieldtype": "Check",
			"default": 1,
			"description": __("Show employees with no timesheet data")
		},
		{
			"fieldname": "chart_type",
			"label": __("Chart Type"),
			"fieldtype": "Select",
			"options": "Department Summary\nTop 50 - Highest Overtime\nTop 50 - Highest Working Hours",
			"default": "Department Summary",
			"description": __("Select chart visualization type")
		}
	],

	"onload": function(report) {
		// Setup chart type filter change listener
		report.page.add_inner_button(__("Refresh Chart"), function() {
			if (report.chart) {
				report.refresh_chart();
			}
		});
		
		// Store reference to report for later use
		window.daily_timesheet_report = report;
		
		// Listen for filter changes to refresh chart
		$(document).off('change', '[data-fieldname="chart_type"]');
		$(document).on('change', '[data-fieldname="chart_type"]', function() {
			// Update global chart type variable
			let new_chart_type = $(this).val() || "Department Summary";
			window.daily_timesheet_chart_type = new_chart_type;
			console.log("Chart type changed to:", new_chart_type);
			
			setTimeout(function() {
				if (report.chart) {
					report.refresh_chart();
				}
			}, 100);
		});
		
		// Initialize chart type from default filter value
		setTimeout(function() {
			let chart_filter = report.get_filter_value("chart_type");
			if (chart_filter) {
				window.daily_timesheet_chart_type = chart_filter;
			}
		}, 500);
	},

	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Color coding for status
		if (column.fieldname == "status") {
			if (value == "Present") {
				if (data.late_entry || data.early_exit) {
					value = `<span style="color: orange; font-weight: bold;">${value}</span>`;
				} else {
					value = `<span style="color: green; font-weight: bold;">${value}</span>`;
				}
			} else if (value == "Sunday") {
				value = `<span style="color: orange; font-weight: bold;">${value}</span>`;
			} else if (value == "Absent") {
				value = `<span style="color: red; font-weight: bold;">${value}</span>`;
			} else if (value == "Half Day") {
				value = `<span style="color: orange; font-weight: bold;">${value}</span>`;
			}
		}

		// Highlight late entry and early exit
		if (column.fieldname == "late_entry" && value == 1) {
			value = `<span style="color: red;">✓</span>`;
		}
		if (column.fieldname == "early_exit" && value == 1) {
			value = `<span style="color: red;">✓</span>`;
		}
		if (column.fieldname == "maternity_benefit" && value == 1) {
			value = `<span style="color: blue;">✓</span>`;
		}

		return value;
	},

	"get_chart_data": function (columns, result) {
		if (!result || result.length === 0) {
			return null;
		}

		// Get chart type from global variable
		let chart_type = window.daily_timesheet_chart_type || "Department Summary";
		
		// Fallback: try to get from report if available
		if (window.daily_timesheet_report && window.daily_timesheet_report.get_filter_value) {
			let filter_value = window.daily_timesheet_report.get_filter_value("chart_type");
			if (filter_value) {
				chart_type = filter_value;
				window.daily_timesheet_chart_type = filter_value; // Update global
			}
		}

		console.log("Chart type selected:", chart_type); // Debug log

		// Helper function to round to 1 decimal place
		function round_decimal(value) {
			return Math.round((value || 0) * 10) / 10;
		}

		if (chart_type === "Top 50 - Highest Overtime") {
			console.log("Rendering Top 50 Overtime chart"); // Debug log
			return get_top_overtime_chart(result, round_decimal);
		} else if (chart_type === "Top 50 - Highest Working Hours") {
			console.log("Rendering Top 50 Working Hours chart"); // Debug log
			return get_top_working_hours_chart(result, round_decimal);
		} else {
			console.log("Rendering Department Summary chart"); // Debug log
			return get_department_summary_chart(result, round_decimal);
		}
	}
};

// Helper functions for different chart types
function get_department_summary_chart(result, round_decimal) {
	// Group by department
	let dept_data = {};

	result.forEach(function (row) {
		let dept = row.department || "No Department";
		if (!dept_data[dept]) {
			dept_data[dept] = {
				working_hours: 0,
				overtime_hours: 0,
				total_hours: 0,
				present_count: 0,
				absent_count: 0
			};
		}

		dept_data[dept].working_hours += row.working_hours || 0;
		dept_data[dept].overtime_hours += row.overtime_hours || 0;
		dept_data[dept].total_hours += row.total_hours || 0;

		if (row.status === "Present" || row.status === "Sunday") {
			dept_data[dept].present_count++;
		} else if (row.status === "Absent") {
			dept_data[dept].absent_count++;
		}
	});

	// Round values
	Object.keys(dept_data).forEach(dept => {
		dept_data[dept].working_hours = round_decimal(dept_data[dept].working_hours);
		dept_data[dept].overtime_hours = round_decimal(dept_data[dept].overtime_hours);
	});

	return {
		data: {
			labels: Object.keys(dept_data),
			datasets: [
				{
					name: "Working Hours",
					values: Object.keys(dept_data).map(dept => dept_data[dept].working_hours)
				},
				{
					name: "Overtime Hours",
					values: Object.keys(dept_data).map(dept => dept_data[dept].overtime_hours)
				}
			]
		},
		type: "bar",
		height: 300,
		colors: ["#36D7B7", "#FF9F43"]
	};
}

function get_top_overtime_chart(result, round_decimal) {
	// Group by employee to sum overtime for each employee
	let employee_data = {};

	result.forEach(function (row) {
		let emp_key = row.employee;
		let emp_name = row.employee_name || row.employee;
		
		if (!employee_data[emp_key]) {
			employee_data[emp_key] = {
				employee: emp_key,
				employee_name: emp_name,
				overtime_hours: 0
			};
		}

		employee_data[emp_key].overtime_hours += row.overtime_hours || 0;
	});

	// Convert to array and sort by overtime hours DESC
	let sorted_employees = Object.values(employee_data)
		.sort((a, b) => (b.overtime_hours || 0) - (a.overtime_hours || 0))
		.slice(0, 50); // Top 50

	// Round values
	sorted_employees.forEach(emp => {
		emp.overtime_hours = round_decimal(emp.overtime_hours);
	});

	return {
		data: {
			labels: sorted_employees.map(emp => emp.employee_name),
			datasets: [
				{
					name: "Overtime Hours",
					values: sorted_employees.map(emp => emp.overtime_hours)
				}
			]
		},
		type: "bar",
		height: 400,
		colors: ["#FF9F43"],
		axisOptions: {
			xIsSeries: false
		},
		barOptions: {
			horizontal: true
		}
	};
}

function get_top_working_hours_chart(result, round_decimal) {
	// Group by employee to sum working hours for each employee
	let employee_data = {};

	result.forEach(function (row) {
		let emp_key = row.employee;
		let emp_name = row.employee_name || row.employee;
		
		if (!employee_data[emp_key]) {
			employee_data[emp_key] = {
				employee: emp_key,
				employee_name: emp_name,
				working_hours: 0
			};
		}

		employee_data[emp_key].working_hours += row.working_hours || 0;
	});

	// Convert to array and sort by working hours DESC
	let sorted_employees = Object.values(employee_data)
		.sort((a, b) => (b.working_hours || 0) - (a.working_hours || 0))
		.slice(0, 50); // Top 50

	// Round values
	sorted_employees.forEach(emp => {
		emp.working_hours = round_decimal(emp.working_hours);
	});

	return {
		data: {
			labels: sorted_employees.map(emp => emp.employee_name),
			datasets: [
				{
					name: "Working Hours",
					values: sorted_employees.map(emp => emp.working_hours)
				}
			]
		},
		type: "bar",
		height: 400,
		colors: ["#36D7B7"],
		axisOptions: {
			xIsSeries: false
		},
		barOptions: {
			horizontal: true
		}
	};
}