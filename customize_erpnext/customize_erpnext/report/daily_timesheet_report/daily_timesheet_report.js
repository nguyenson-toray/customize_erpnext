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
			"default": "Single Date",
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
						'custom_section': ['like', '%' + txt + '%'],
						'custom_section': ['is', 'set']  // Exclude NULL values
					},
					group_by: 'custom_section'
				}).then(function (data) {
					return data.filter(function (item) {
						// Filter out null, undefined, empty string
						return item.custom_section && item.custom_section.trim() !== '';
					}).map(function (item) {
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
						'custom_group': ['like', '%' + txt + '%'],
						'custom_group': ['is', 'set']  // Exclude NULL values
					},
					group_by: 'custom_group'
				}).then(function (data) {
					return data.filter(function (item) {
						// Filter out null, undefined, empty string
						return item.custom_group && item.custom_group.trim() !== '';
					}).map(function (item) {
						return {
							value: item.custom_group,
							label: item.custom_group
						};
					});
				});
			}
		},
		// {
		// 	"fieldname": "employee",
		// 	"label": __("Employee"),
		// 	"fieldtype": "Link",
		// 	"options": "Employee"
		// },
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
			"fieldname": "chart_type",
			"label": __("Chart Type"),
			"fieldtype": "Select",
			"options": "Department Summary\nTop 50 - Highest Overtime\nTop 50 - Highest Working Hours",
			"default": "Top 50 - Highest Overtime",
			"description": __("Select chart visualization type"),
			"depends_on": "eval:doc.date_type!='Single Date'"
		}
	],

	"onload": function (report) {
		// Setup chart type filter change listener
		report.page.add_inner_button(__("Refresh Chart"), function () {
			if (report.chart) {
				report.refresh_chart();
			}
		});

		// Store reference to report for later use
		window.daily_timesheet_report = report;

		// Listen for filter changes to refresh chart
		$(document).off('change', '[data-fieldname="chart_type"]');
		$(document).on('change', '[data-fieldname="chart_type"]', function () {
			// Update global chart type variable
			let new_chart_type = $(this).val() || "Department Summary";
			window.daily_timesheet_chart_type = new_chart_type;
			console.log("Chart type changed to:", new_chart_type);

			setTimeout(function () {
				if (report.chart) {
					report.refresh_chart();
				}
			}, 100);
		});

		// Initialize chart type from default filter value
		setTimeout(function () {
			let chart_filter = report.get_filter_value("chart_type");
			if (chart_filter) {
				window.daily_timesheet_chart_type = chart_filter;
			}
		}, 500);

		// Add export Excel button (always shown)
		report.page.add_inner_button(__('⬇️1. Export Excel - C&B Template'), function () {
			export_timesheet_excel(report);
		},); // __('Actions'));

		// Add send daily timesheet report button
		report.page.add_inner_button(__('📩2. Send Report'), function () {
			send_daily_timesheet_report_dialog(report);
		},); //__('Actions'));


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

		// Show pie chart for Single Date - Status distribution (only if not summary mode)
		if (window.daily_timesheet_report && window.daily_timesheet_report.get_filter_value) {
			let date_type = window.daily_timesheet_report.get_filter_value("date_type");
			let is_summary = window.daily_timesheet_report.get_filter_value("summary");

			// Only show pie chart if Single Date AND NOT summary mode
			if (date_type === "Single Date" && !is_summary) {
				return get_status_distribution_chart(result);
			}

			// Hide chart if summary mode is enabled
			if (is_summary) {
				return null;
			}
		}

		// Get chart type from global variable for other date types
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
	},

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
		height: 150,
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
				custom_group: row.custom_group || 'N/A',
				overtime_hours: 0
			};
		}

		employee_data[emp_key].overtime_hours += row.overtime_hours || 0;
	});

	// Convert to array and sort by overtime hours DESC
	let sorted_employees = Object.values(employee_data)
		.sort((a, b) => (b.overtime_hours || 0) - (a.overtime_hours || 0))
		.slice(0, 50); // Top 50

	// Create separate datasets for each color category
	let green_employees = [];
	let orange_employees = [];
	let red_employees = [];
	let all_labels = [];

	sorted_employees.forEach(emp => {
		emp.overtime_hours = round_decimal(emp.overtime_hours);

		// Simple label - just employee name
		all_labels.push(emp.employee_name);

		// Categorize by Final OT ranges
		if (emp.overtime_hours <= 30) {
			green_employees.push(emp.overtime_hours);
			orange_employees.push(0);
			red_employees.push(0);
		} else if (emp.overtime_hours > 30 && emp.overtime_hours <= 40) {
			green_employees.push(0);
			orange_employees.push(emp.overtime_hours);
			red_employees.push(0);
		} else {
			green_employees.push(0);
			orange_employees.push(0);
			red_employees.push(emp.overtime_hours);
		}
	});

	return {
		data: {
			labels: all_labels,
			datasets: [
				{
					name: "≤ 30 hours",
					values: green_employees
				},
				{
					name: "30-40 hours",
					values: orange_employees
				},
				{
					name: "> 40 hours",
					values: red_employees
				}
			]
		},
		type: "bar",
		height: 150,
		colors: ["#28a745", "#fd7e14", "#dc3545"],
		axisOptions: {
			xIsSeries: false
		},
		barOptions: {
			horizontal: true
		},
		tooltipOptions: {
			formatTooltipX: function (label) {
				return label; // Employee Name
			},
			formatTooltipY: function (value, label, index) {
				// Only show non-zero values
				if (value && value > 0) {
					return value + " hours";
				}
				return null; // Hide zero values
			}
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
		height: 150,
		colors: ["#36D7B7"],
		axisOptions: {
			xIsSeries: false
		},
		barOptions: {
			horizontal: true
		}
	};
}

function get_status_distribution_chart(result) {
	// Count employees by status
	let status_counts = {
		'Present': 0,
		'Absent': 0,
		'Maternity Leave': 0
	};

	result.forEach(function (row) {
		let status = row.status;
		if (status && status_counts.hasOwnProperty(status)) {
			status_counts[status]++;
		}
	});

	// Calculate total active employees
	let total = status_counts['Present'] + status_counts['Absent'] + status_counts['Maternity Leave'];

	// Calculate percentages
	let present_pct = total > 0 ? Math.round((status_counts['Present'] / total) * 100) : 0;
	let absent_pct = total > 0 ? Math.round((status_counts['Absent'] / total) * 100) : 0;
	let maternity_pct = total > 0 ? Math.round((status_counts['Maternity Leave'] / total) * 100) : 0;

	return {
		data: {
			labels: [
				`Present: ${status_counts['Present']} (${present_pct}%)`,
				`Absent: ${status_counts['Absent']} (${absent_pct}%)`,
				`Maternity Leave: ${status_counts['Maternity Leave']} (${maternity_pct}%)`
			],
			datasets: [
				{
					name: `Total Active: ${total}`,
					values: [
						status_counts['Present'],
						status_counts['Absent'],
						status_counts['Maternity Leave']
					]
				}
			]
		},
		type: "percentage",  // Donut chart
		height: 300,
		colors: ["#28a745", "#E20E20", "#FF69B4"],  // Green for Present, Red for Absent, Pink for Maternity
		maxSlices: 10,
		truncateLegends: false,
		tooltipOptions: {
			formatTooltipY: d => d + ""
		},
		title: `Total Active Employees: ${total}`
	};
}

// Send Daily Timesheet Report dialog function
function send_daily_timesheet_report_dialog(report) {
	// Get current filters to suggest default date
	let filters = report.get_values();
	let default_date = frappe.datetime.get_today();

	// Try to get date from current filters
	if (filters.date_type === 'Single Date' && filters.single_date) {
		default_date = filters.single_date;
	}

	// Create dialog
	let d = new frappe.ui.Dialog({
		title: __('Send Daily Timesheet Report'),
		fields: [
			{
				fieldname: 'report_date',
				label: __('Report Date'),
				fieldtype: 'Date',
				default: default_date,
				reqd: 1,
				description: __('Select the date for the report')
			},
			{
				fieldname: 'recipients',
				label: __('Email Recipients'),
				fieldtype: 'Small Text',
				reqd: 1,
				default: 'it@tiqn.com.vn\nni.nht@tiqn.com.vn\nhoanh.ltk@tiqn.com.vn\nloan.ptk@tiqn.com.vn',
				description: __('Enter one email address per line')
			}
		],
		primary_action_label: __('Send Report'),
		primary_action: function (values) {
			// Validate email format - split by newlines or commas
			let emails = values.recipients.split(/[\n,]/).map(e => e.trim()).filter(e => e.length > 0);
			let invalid_emails = emails.filter(e => !frappe.utils.validate_type(e, 'email'));

			if (invalid_emails.length > 0) {
				frappe.msgprint({
					title: __('Invalid Email'),
					message: __('Please enter valid email addresses: ') + invalid_emails.join(', '),
					indicator: 'red'
				});
				return;
			}

			// Disable dialog and show loading
			d.get_primary_btn().prop('disabled', true);
			d.get_primary_btn().html(__('Sending...'));

			// // Show loading indicator
			// frappe.show_alert({
			// 	message: __('Sending report, please wait...'),
			// 	indicator: 'blue'
			// });

			// Freeze all fields in dialog
			d.fields_dict.report_date.df.read_only = 1;
			d.fields_dict.recipients.df.read_only = 1;
			d.fields_dict.report_date.refresh();
			d.fields_dict.recipients.refresh();

			// Call server method to send report
			frappe.call({
				method: 'customize_erpnext.customize_erpnext.report.daily_timesheet_report.scheduler.send_daily_time_sheet_report',
				args: {
					report_date: values.report_date,
					recipients: values.recipients
				},
				freeze: true,
				freeze_message: __('📨 Sending Daily Timesheet Report...'),
				callback: function (r) {
					if (r.message && r.message.status === 'success') {
						frappe.show_alert({
							message: __('Report sent successfully!'),
							indicator: 'green'
						}, 5);
						// Auto close dialog on success
						d.hide();
					} else {
						frappe.msgprint({
							title: __('Error'),
							message: r.message ? r.message.message : __('Failed to send report. Please check the error log.'),
							indicator: 'red'
						});
						// Re-enable dialog on error
						d.get_primary_btn().prop('disabled', false);
						d.get_primary_btn().html(__('Send Report'));
						d.fields_dict.report_date.df.read_only = 0;
						d.fields_dict.recipients.df.read_only = 0;
						d.fields_dict.report_date.refresh();
						d.fields_dict.recipients.refresh();
					}
				},
				error: function () {
					frappe.msgprint({
						title: __('Error'),
						message: __('Failed to send report. Please try again or contact administrator.'),
						indicator: 'red'
					});
					// Re-enable dialog on error
					d.get_primary_btn().prop('disabled', false);
					d.get_primary_btn().html(__('Send Report'));
					d.fields_dict.report_date.df.read_only = 0;
					d.fields_dict.recipients.df.read_only = 0;
					d.fields_dict.report_date.refresh();
					d.fields_dict.recipients.refresh();
				}
			});
		}
	});

	d.show();
}

// Export Excel function
function export_timesheet_excel(report) {
	let filters = report.get_values();

	// Validate required date filters based on date type
	if (!filters.date_type) {
		frappe.msgprint({
			title: __('Missing Filter'),
			message: __('Please select a Date Type for the export.'),
			indicator: 'red'
		});
		return;
	}

	if (filters.date_type === 'Single Date' && !filters.single_date) {
		frappe.msgprint({
			title: __('Missing Filter'),
			message: __('Please select a Date for the export.'),
			indicator: 'red'
		});
		return;
	}

	if (filters.date_type === 'Date Range' && (!filters.from_date || !filters.to_date)) {
		frappe.msgprint({
			title: __('Missing Filters'),
			message: __('Please select From Date and To Date for the export.'),
			indicator: 'red'
		});
		return;
	}

	if (filters.date_type === 'Monthly' && (!filters.month || !filters.year)) {
		frappe.msgprint({
			title: __('Missing Filters'),
			message: __('Please select Month and Year for the export.'),
			indicator: 'red'
		});
		return;
	}

	frappe.show_alert({
		message: __('Generating Excel file...'),
		indicator: 'blue'
	});

	// Get current report data 
	let report_data = null;
	if (report.data && report.data.length > 0) {
		report_data = report.data;
	}

	frappe.call({
		method: 'customize_erpnext.customize_erpnext.report.daily_timesheet_report.daily_timesheet_report.export_timesheet_excel',
		args: {
			filters: filters,
			report_data: report_data
		},
		callback: function (r) {
			if (r.message && r.message.filecontent) {
				// Convert base64 to blob
				const byteCharacters = atob(r.message.filecontent);
				const byteNumbers = new Array(byteCharacters.length);
				for (let i = 0; i < byteCharacters.length; i++) {
					byteNumbers[i] = byteCharacters.charCodeAt(i);
				}
				const byteArray = new Uint8Array(byteNumbers);
				const blob = new Blob([byteArray], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });

				// Create download link
				const url = window.URL.createObjectURL(blob);
				const link = document.createElement('a');
				link.href = url;
				link.download = r.message.filename;
				document.body.appendChild(link);
				link.click();
				document.body.removeChild(link);
				window.URL.revokeObjectURL(url);

				frappe.show_alert({
					message: __('Excel file downloaded successfully!'),
					indicator: 'green'
				});
			}
		},
		error: function () {
			frappe.msgprint({
				title: __('Export Error'),
				message: __('Failed to generate Excel file. Please try again.'),
				indicator: 'red'
			});
		}
	});
}