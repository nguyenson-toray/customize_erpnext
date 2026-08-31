// Copyright (c) 2025, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Shift Attendance Customize"] = {
	onload: function (report) {
		// Add export Excel button
		report.page.add_inner_button(__('⬇️1. Export Excel'), function () {
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
		size: 'large',
		fields: [
			{ fieldtype: 'Section Break', label: __('Hours') },
			{
				fieldname: 'with_leave_application',
				label: __('With Leave Application'),
				fieldtype: 'Check',
				default: 1,
				on_change: function () {
					// =1 thì sheet đơn nghỉ luôn được xuất -> tích sẵn và khoá lại, cho dialog
					// không nói một đằng mà file ra một nẻo.
					const on = !!d.get_value('with_leave_application');
					if (on) { d.set_value('sheet_leave_application', 1); }
					d.set_df_property('sheet_leave_application', 'read_only', on ? 1 : 0);
					// HTML field: set thang qua $wrapper, set_df_property('options') khong re-render.
					const hint = d.get_field('hours_mode_hint');
					if (hint) {
						hint.$wrapper.html(
							`<div class="text-muted small" style="margin:-8px 0 4px 0">${on
								? __('Working Hours (capped by leave) + leave codes on Timesheet. Leave Application sheet always included.')
								: __('Actual Working Hours everywhere, no leave codes, no Actual column on Detail.')
							}</div>`);
					}
				}
			},
			{ fieldname: 'hours_mode_hint', fieldtype: 'HTML' },
			{ fieldtype: 'Section Break', label: __('Employees') },
			{
				fieldname: 'only_resigned',
				label: __('Only employees who resigned in this period'),
				fieldtype: 'Check',
				default: 0,
				description: __('Relieving date inside From-To. Not the same as status Left.')
			},
			{
				fieldname: 'split_department',
				label: __('Split by Department'),
				fieldtype: 'Check',
				default: 0,
				description: __('Group employees under department headers')
			},
			{ fieldtype: 'Column Break' },
			{
				fieldname: 'sort_order',
				label: __('Sort by Employee'),
				fieldtype: 'Select',
				options: 'Ascending\nDescending',
				default: 'Ascending'
			},
			{
				// Chênh dưới ngưỡng là nhiễu làm tròn (4,01h vs 4,00h = 36 giây), không phải
				// "đi làm dù có phép". Đo được: 95/312 ca bị chặn chỉ chênh dưới 15 phút.
				fieldname: 'leave_gap_minutes',
				label: __('Important Note: report leave-but-worked from'),
				fieldtype: 'Select',
				options: '0\n15\n30\n60\n120\n180\n240\n240+',
				default: '15',
				description: __('Minutes of gap before a day is listed. 0 = list everything.')
			},
			{ fieldtype: 'Section Break', label: __('Sheets to export') },
			{ fieldname: 'sheet_important_note', label: __('Important Note'), fieldtype: 'Check', default: 1 },
			{ fieldname: 'sheet_detail', label: __('Detail'), fieldtype: 'Check', default: 1 },
			{ fieldname: 'sheet_summary', label: __('Summary'), fieldtype: 'Check', default: 1 },
			{ fieldname: 'sheet_leave_application', label: __('Leave Application'), fieldtype: 'Check', default: 1 },
			{ fieldtype: 'Column Break' },
			{ fieldname: 'sheet_timesheet', label: __('Timesheet'), fieldtype: 'Check', default: 1 },
			{ fieldname: 'sheet_overtime', label: __('Overtime'), fieldtype: 'Check', default: 1 },
			{ fieldname: 'sheet_shift', label: __('Shift'), fieldtype: 'Check', default: 1 },
			{ fieldname: 'sheet_la', label: __('LA'), fieldtype: 'Check', default: 1 }
		],
		primary_action_label: __('Export'),
		primary_action: function (values) {
			// "240+" không phải số — quy về một ngưỡng đủ lớn để chỉ còn ca chênh gần trọn ca
			filters.leave_gap_minutes = values.leave_gap_minutes === '240+'
				? 241 : cint(values.leave_gap_minutes);

			const sheet_map = {
				sheet_important_note: 'Important Note',
				sheet_detail: 'Detail',
				sheet_summary: 'Summary',
				sheet_leave_application: 'Leave Application',
				sheet_timesheet: 'Timesheet',
				sheet_overtime: 'Overtime',
				sheet_shift: 'Shift'
			};
			const picked = Object.keys(sheet_map).filter((k) => values[k]).map((k) => sheet_map[k]);
			if (!picked.length) {
				frappe.msgprint({
					title: __('No sheet selected'),
					message: __('Please tick at least one sheet to export.'),
					indicator: 'red'
				});
				return;
			}
			filters.export_sheets = picked.join(',');

			d.hide();

			// Add export options to filters
			filters.split_department = values.split_department ? 1 : 0;
			filters.sort_order = values.sort_order;
			filters.only_resigned = values.only_resigned ? 1 : 0;
			filters.with_leave_application = values.with_leave_application ? 1 : 0;

			// Call the actual export function
			do_export_attendance_excel(filters);
		}
	});

	d.show();
	d.fields_dict.with_leave_application.df.on_change();

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
function _reset_dialog_fields(d) {
	d.get_primary_btn().prop('disabled', false);
	d.get_primary_btn().html(__('Send Report'));
	['report_date', 'recipients', 'force_update_attendance'].forEach(f => {
		if (d.fields_dict[f]) {
			d.fields_dict[f].df.read_only = 0;
			d.fields_dict[f].refresh();
		}
	});
}

function send_attendance_report_dialog(report) {
	// Suggest the date currently filtered in the report
	let filters = report.get_values();
	let default_date = filters.from_date || frappe.datetime.get_today();

	// Recipients are typed in deliberately. The Manager / HR lists on Attendance
	// Calculation Setting drive the scheduled send only, so sending by hand from
	// here cannot reach the real audience by accident.
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
				fieldname: 'attach_detail',
				label: __('Attach file detail'),
				fieldtype: 'Check',
				default: 0,
				description: __('Adds the detailed Excel workbook for this date.')
			},
			{
				fieldname: 'force_update_attendance',
				label: __('Force Update Attendance'),
				fieldtype: 'Check',
				default: 0,
				// Not tied to the attachment: recalculating rebuilds the Attendance
				// records the summary figures are read from too.
				description: __('Rebuilds attendance from check-ins. Affects every figure, not just the attachment.')
			},
			{
				fieldtype: 'Section Break'
			},
			{
				fieldname: 'recipients',
				label: __('Email Recipients'),
				fieldtype: 'Small Text',
				reqd: 1,
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

			d.get_primary_btn().prop('disabled', true);

			frappe.call({
				method: 'customize_erpnext.api.daily_attendance_email.send_daily_attendance_email',
				args: {
					date: values.report_date,
					recipients: values.recipients,
					attach_detail: values.attach_detail ? 1 : 0,
					force_update_attendance: values.force_update_attendance ? 1 : 0,
					bypass_holiday_check: 1
				},
				// No freeze: the work runs in a background job, so the dialog
				// closes immediately instead of holding the user on a spinner
				// through an attendance rebuild.
				callback: function (r) {
					let res = r.message || {};
					if (res.status === 'queued') {
						d.hide();
						frappe.show_alert({
							message: __('Report queued for {0}. The email will arrive shortly.', [(res.recipients || []).join(', ')]),
							indicator: 'green'
						}, 10);
					} else {
						frappe.msgprint({
							title: __('Not Sent'),
							message: res.message || __('Failed to send report. Please check the error log.'),
							indicator: res.status === 'skipped' ? 'orange' : 'red'
						});
						_reset_dialog_fields(d);
					}
				},
				error: function () {
					frappe.msgprint({
						title: __('Error'),
						message: __('Failed to send report. Please try again or contact administrator.'),
						indicator: 'red'
					});
					_reset_dialog_fields(d);
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
