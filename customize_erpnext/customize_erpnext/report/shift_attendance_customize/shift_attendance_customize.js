// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Shift Attendance Customize"] = {
	onload: function (report) {
		// Add export Excel button
		report.page.add_inner_button(__('⬇️1. Export Excel - C&B Template'), function () {
			export_attendance_excel(report);
		});

		// Add send report button
		report.page.add_inner_button(__('📩2. Send Report'), function () {
			send_attendance_report_dialog(report);
		});

		// Add bulk update attendance button
		report.page.add_inner_button(__('🔄3. Bulk Update Attendance'), function () {
			show_bulk_update_attendance(report);
		});
	},
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
			// function () {
			// 	// Default to 26th of previous month
			// 	let date = frappe.datetime.get_today();
			// 	let current_day = frappe.datetime.str_to_obj(date).getDate();

			// 	// If current day is before 26th, go back to 26th of month before last
			// 	if (current_day < 26) {
			// 		date = frappe.datetime.add_months(date, -2);
			// 	} else {
			// 		date = frappe.datetime.add_months(date, -1);
			// 	}

			// 	// Set to 26th
			// 	let year = frappe.datetime.str_to_obj(date).getFullYear();
			// 	let month = frappe.datetime.str_to_obj(date).getMonth();
			// 	return frappe.datetime.obj_to_str(new Date(year, month, 26));
			// }(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "shift",
			label: __("Shift Type"),
			fieldtype: "Link",
			options: "Shift Type",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Present", "Absent", "On Leave", "Half Day", "Work From Home"],
		},
		{
			fieldname: "group",
			label: __("Group"),
			fieldtype: "Link",
			options: "Group",
			get_query: function () {
				return {
					filters: {
						"docstatus": ["!=", 2]
					}
				};
			}
		},
		{
			fieldname: "late_entry",
			label: __("Late Entry"),
			fieldtype: "Check",
		},
		{
			fieldname: "early_exit",
			label: __("Early Exit"),
			fieldtype: "Check",
		},
		{
			fieldname: "detail_join_resign_date",
			label: __("Show Detail Join / Resign Date"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "summary",
			label: __("Summary"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				// When Summary is checked, auto-check Detail Join / Resign Date
				if (frappe.query_report.get_filter_value('summary')) {
					frappe.query_report.set_filter_value('detail_join_resign_date', 1);
				}
				// Refresh report when Summary changes
				frappe.query_report.refresh();
			}
		},
		{
			fieldname: "show_leave_application",
			label: __("Show Leave Application"),
			fieldtype: "Check",
			default: 0,
			on_change: function () {
				// Refresh report to show/hide leave columns
				frappe.query_report.refresh();
			}
		},
	],
	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);
		if (
			(column.fieldname === "in_time" && data.late_entry) ||
			(column.fieldname === "out_time" && data.early_exit)
		) {
			value = `<span style='color:red!important'>${value}</span>`;
		}
		return value;
	},
};

// Export Excel function
function export_attendance_excel(report) {
	let filters = report.get_values();

	// Validate required date filters
	if (!filters.from_date || !filters.to_date) {
		frappe.msgprint({
			title: __('Missing Filters'),
			message: __('Please select From Date and To Date for the export.'),
			indicator: 'red'
		});
		return;
	}

	// Show export options dialog
	let d = new frappe.ui.Dialog({
		title: __('Export Excel Options'),
		fields: [
			{
				fieldname: 'split_department',
				label: __('Split by Department'),
				fieldtype: 'Check',
				default: 0,
				description: __('Group employees by department with department headers')
			},
			{
				fieldname: 'sort_order',
				label: __('Sort by Employee'),
				fieldtype: 'Select',
				options: 'Ascending\nDescending',
				default: 'Ascending',
				description: __('Sort order for employee names')
			}
		],
		primary_action_label: __('Export'),
		primary_action: function (values) {
			d.hide();

			// Add export options to filters
			filters.split_department = values.split_department ? 1 : 0;
			filters.sort_order = values.sort_order;

			// Call the actual export function
			do_export_attendance_excel(filters);
		}
	});

	d.show();
}

// Actual export function (separated from dialog)
function do_export_attendance_excel(filters) {
	console.log('do_export_attendance_excel called with filters:', filters);

	// Listen for background export completion
	frappe.realtime.on('excel_export_complete', function (data) {
		if (data.success) {
			// Auto-download using iframe
			let iframe = document.createElement('iframe');
			iframe.style.display = 'none';
			iframe.src = data.file_url;
			document.body.appendChild(iframe);

			setTimeout(() => {
				document.body.removeChild(iframe);
			}, 5000);

			frappe.show_alert({
				message: __('Excel file downloaded successfully!'),
				indicator: 'green'
			}, 5);
		} else {
			frappe.msgprint({
				title: __('Export Error'),
				message: data.message || __('Failed to generate Excel file.'),
				indicator: 'red'
			});
		}
	});

	frappe.call({
		method: 'customize_erpnext.customize_erpnext.report.shift_attendance_customize.shift_attendance_customize.export_attendance_excel',
		args: {
			filters: filters
		},
		freeze: true,
		freeze_message: __('Generating Excel file...'),
		callback: function (r) {
			console.log('Export API response:', r);
			if (r.message) {
				console.log('Response message:', r.message);
				// Check if it's a background job
				if (r.message.background_job) {
					frappe.show_alert({
						message: r.message.message || __('Large export queued for background processing. You will be notified when ready.'),
						indicator: 'blue'
					}, 15);
				} else if (r.message.file_url) {
					// Immediate response - small dataset
					console.log('Downloading file from:', r.message.file_url);

					// Auto-download using iframe (avoids popup blockers)
					let iframe = document.createElement('iframe');
					iframe.style.display = 'none';
					iframe.src = r.message.file_url;
					document.body.appendChild(iframe);

					// Clean up iframe after download starts
					setTimeout(() => {
						document.body.removeChild(iframe);
					}, 5000);

					frappe.show_alert({
						message: __('Excel file downloaded successfully!'),
						indicator: 'green'
					}, 5);
				} else {
					console.log('No file_url or background_job in response');
				}
			} else {
				console.log('No r.message in response, full response:', r);
			}
		},
		error: function (r) {
			console.log('Export API error:', r);
			let error_message = __('Failed to generate Excel file. Please try again.');

			// Check for specific error messages
			if (r && r._server_messages) {
				try {
					let messages = JSON.parse(r._server_messages);
					if (messages && messages.length > 0) {
						let parsed = JSON.parse(messages[0]);
						if (parsed && parsed.message) {
							error_message = parsed.message;
						}
					}
				} catch (e) {
					// Use default error message
				}
			}

			frappe.msgprint({
				title: __('Export Error'),
				message: error_message,
				indicator: 'red'
			});
		}
	});
}

// Send Attendance Report dialog function
function send_attendance_report_dialog(report) {
	// Get current filters to suggest default date
	let filters = report.get_values();
	let default_date = frappe.datetime.get_today();

	// Try to get date from current filters
	if (filters.from_date) {
		default_date = filters.from_date;
	}

	// Create dialog
	let d = new frappe.ui.Dialog({
		title: __('Send Daily Attendance Report'),
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
				default: "it@tiqn.com.vn\nhoanh.ltk@tiqn.com.vn\nloan.ptk@tiqn.com.vn\nni.nht@tiqn.com.vn\nbinh.dtt@tiqn.com.vn",
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

			// Freeze all fields in dialog
			d.fields_dict.report_date.df.read_only = 1;
			d.fields_dict.recipients.df.read_only = 1;
			d.fields_dict.report_date.refresh();
			d.fields_dict.recipients.refresh();

			// Call server method to send report
			frappe.call({
				method: 'customize_erpnext.customize_erpnext.report.shift_attendance_customize.scheduler.send_daily_attendance_report',
				args: {
					report_date: values.report_date,
					recipients: values.recipients
				},
				freeze: true,
				freeze_message: __('📨 Sending Daily Attendance Report...'),
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

// ============================================================================
// BULK UPDATE ATTENDANCE - Redirect to Attendance List
// ============================================================================

function show_bulk_update_attendance(report) {
	frappe.msgprint({
		title: __('🔄 Bulk Update Attendance'),
		message: `
			<div class="alert alert-info mb-3">
				<h6 class="alert-heading"><i class="fa fa-info-circle"></i> ${__('Use Feature from Attendance List')}</h6>
				<p class="mb-2">${__('To bulk update attendance records, please use the <strong>"🔄 Bulk Update Attendance"</strong> feature from the Attendance List page.')}</p>
				<p class="mb-0">${__('This feature provides comprehensive filtering options and supports updates by:')}</p>
				<ul class="mb-2 mt-2">
					<li>${__('Date Range')}</li>
					<li>${__('Specific Employee')}</li>
					<li>${__('Employee Group')}</li>
					<li>${__('All Active Employees')}</li>
				</ul>
			</div>

			<div class="text-center mt-3">
				<a href="/app/attendance" class="btn btn-primary btn-lg" target="_blank">
					<i class="fa fa-external-link"></i> ${__('Open Attendance List')}
				</a>
			</div>

			<p class="text-muted mt-3 mb-0 text-center">
				<small><i class="fa fa-lightbulb-o"></i> ${__('After updating, you can return here to view the report')}</small>
			</p>
		`,
		indicator: 'blue',
		wide: true
	});
}
