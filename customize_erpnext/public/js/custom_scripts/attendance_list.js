/**
 * Monkey Patch for Attendance List - Override "Mark Attendance" button
 * Keep HRMS logic, only add "All Active Employees" option
 */

// Constants
const BULK_ATTENDANCE_ASYNC_THRESHOLD = 1000; // Records threshold for async processing

// Save original HRMS listview settings
const original_attendance_listview = frappe.listview_settings['Attendance'] || {};

// Override with custom implementation
frappe.listview_settings['Attendance'] = {
	// Keep original fields and indicator
	add_fields: original_attendance_listview.add_fields || ["status", "attendance_date"],

	get_indicator: original_attendance_listview.get_indicator || function (doc) {
		if (["Present", "Work From Home"].includes(doc.status)) {
			return [__(doc.status), "green", "status,=," + doc.status];
		} else if (["Absent", "On Leave"].includes(doc.status)) {
			return [__(doc.status), "red", "status,=," + doc.status];

		} else if (["Maternity Leave"].includes(doc.status)) {
			return [__(doc.status), "purple", "status,=," + doc.status];
		} else if (doc.status == "Half Day") {
			return [__(doc.status), "orange", "status,=," + doc.status];
		}
	},

	// Override onload to replace Mark Attendance button
	onload: function (list_view) {
		let me = this;
		if (frappe.perm.has_perm("Attendance", 0, "create")) {
			list_view.page.add_inner_button(__("Bulk Update Attendance"), function () {
				show_bulk_update_attendance(list_view, me);
			});

		}
	},

	// Keep HRMS helper methods
	reset_dialog: original_attendance_listview.reset_dialog,
	get_unmarked_days: original_attendance_listview.get_unmarked_days
};

// ============================================================================
// BULK UPDATE ATTENDANCE V2 - Optimized (Daily Timesheet Pattern)
// ============================================================================

/** Build MM/YYYY option list descending from current month to 01/2026 */
function _month_options() {
	const today = frappe.datetime.get_today();
	const [cy, cm] = today.split('-').map(Number);
	const opts = ['']; // first blank = custom
	let y = cy, m = cm;
	while (y > 2025 || (y === 2025 && m >= 1)) {
		opts.push(String(m).padStart(2, '0') + '/' + y);
		if (--m === 0) { m = 12; y--; }
	}
	return opts.join('\n');
}

/** Convert MM/YYYY → { from_date: YYYY-MM-26 (prev month), to_date: YYYY-MM-25 } */
function _month_to_range(mmyyyy) {
	const [mm, yyyy] = mmyyyy.split('/').map(Number);
	let pm = mm - 1, py = yyyy;
	if (pm === 0) { pm = 12; py--; }
	return {
		from_date: `${py}-${String(pm).padStart(2, '0')}-26`,
		to_date: `${yyyy}-${String(mm).padStart(2, '0')}-25`
	};
}

function show_bulk_update_attendance(list_view, me) {
	let _syncing = false; // prevent circular onchange triggers

	let dialog = new frappe.ui.Dialog({
		title: __("Bulk Update Attendance"),
		size: 'large',
		fields: [
			{
				fieldtype: 'Section Break',
				label: __('Date Range')
			},
			{
				fieldtype: 'Select',
				fieldname: 'month_preset',
				label: __('Month'),
				options: _month_options(),
				onchange: function () {
					const val = dialog.get_value('month_preset');
					if (!val || _syncing) return;
					_syncing = true;
					const { from_date, to_date } = _month_to_range(val);
					const today = frappe.datetime.get_today();
					dialog.set_value('from_date', from_date);
					dialog.set_value('to_date', to_date > today ? today : to_date);
					_syncing = false;
				}
			},
			{
				fieldtype: 'Column Break'
			},
			{
				fieldtype: 'HTML',
				options: '<div style="padding-top:22px;color:#8d99a6;font-size:12px">'
					+ __('Or set dates manually below') + '</div>'
			},
			{
				fieldtype: 'Section Break'
			},
			{
				fieldtype: 'Date',
				fieldname: 'from_date',
				label: __('From Date'),
				default: frappe.datetime.get_today(),
				reqd: 1,
				onchange: function () {
					if (!_syncing) dialog.set_value('month_preset', '');
				}
			},
			{
				fieldtype: 'Column Break'
			},
			{
				fieldtype: 'Date',
				fieldname: 'to_date',
				label: __('To Date'),
				default: frappe.datetime.get_today(),
				reqd: 1,
				onchange: function () {
					if (!_syncing) dialog.set_value('month_preset', '');
					// Clamp to today if future date entered manually
					const today = frappe.datetime.get_today();
					if (dialog.get_value('to_date') > today) {
						_syncing = true;
						dialog.set_value('to_date', today);
						_syncing = false;
					}
				}
			},
			{
				fieldtype: 'Section Break',
				label: __('Employee Filter (Optional)')
			},
			{
				fieldtype: 'Link',
				fieldname: 'employee',
				label: __('Employee (Leave empty for all)'),
				options: 'Employee',
				onchange: function () {
					if (dialog.custom_group != null) dialog.set_value('custom_group', null);
				}
			},
			{
				fieldtype: 'Column Break'
			},
			{
				fieldtype: 'Link',
				fieldname: 'custom_group',
				label: __('Employee Group (Leave empty for all)'),
				options: 'Group',
				onchange: function () {
					dialog.set_value('employee', null);
				}
			}
		],
		primary_action_label: __('Update Attendance'),
		primary_action: async function (values) {
			// Validation
			if (values.from_date > values.to_date) {
				frappe.msgprint(__('From Date cannot be greater than To Date'));
				return;
			}

			let days_diff = frappe.datetime.get_diff(values.to_date, values.from_date);
			if (days_diff > 92) { // ~3 months max for performance reasons
				frappe.msgprint(__('Date range too large. Maximum 92 days recommended for optimal performance.'));
				return;
			}

			// Handle custom_group filter
			let employee_list = null;
			let employee_count = 0;

			if (values.custom_group) {
				try {
					// Get employees in group that are active in date range
					const response = await frappe.call({
						method: "customize_erpnext.api.employee.employee_utils.get_employees_active_in_date_range",
						args: {
							from_date: values.from_date,
							to_date: values.to_date,
							custom_group: values.custom_group
						}
					});

					if (response.message && response.message.length > 0) {
						employee_list = response.message;
						employee_count = employee_list.length;
						console.log(`Custom group '${values.custom_group}' has ${employee_count} active employees in date range`);
					} else {
						frappe.msgprint(__('No active employees found in group "{0}" for the selected date range', [values.custom_group]));
						return;
					}
				} catch (error) {
					frappe.msgprint(__('Error fetching employees for group: {0}', [error.message]));
					return;
				}
			} else if (values.employee) {
				employee_list = [values.employee];
				employee_count = 1;
			} else {
				// Get all employees active in date range
				try {
					const response = await frappe.call({
						method: "customize_erpnext.api.employee.employee_utils.get_employees_active_in_date_range",
						args: {
							from_date: values.from_date,
							to_date: values.to_date
						}
					});
					employee_count = response.message ? response.message.length : 0;
					console.log(`All employees: ${employee_count} active in date range`);
				} catch (error) {
					console.error("Error counting employees:", error);
					frappe.msgprint(__('Error fetching employees: {0}', [error.message]));
					return;
				}
			}

			// Calculate total records (employees × days)
			let days_count = days_diff + 1;
			let total_records = employee_count * days_count;

			console.log(`Processing: ${employee_count} employees × ${days_count} days = ${total_records} records`);

			// Build confirmation message
			let msg;
			if (values.custom_group) {
				msg = __('Update attendance for {0} employees in group "{1}" from {2} to {3}?', [
					employee_count,
					values.custom_group,
					frappe.datetime.str_to_user(values.from_date),
					frappe.datetime.str_to_user(values.to_date),
					employee_count,
					days_count,
					total_records
				]);
			} else if (values.employee) {
				msg = __('Update attendance for employee {0} from {1} to {2}?', [
					values.employee,
					frappe.datetime.str_to_user(values.from_date),
					frappe.datetime.str_to_user(values.to_date)
				]);
			} else {
				msg = __('Update attendance for ALL {0} active employees from {1} to {2}?', [
					employee_count,
					frappe.datetime.str_to_user(values.from_date),
					frappe.datetime.str_to_user(values.to_date),
					employee_count,
					days_count,
					total_records
				]);
			}

			frappe.confirm(msg, function () {
				// Both paths now use bulk_update_attendance_v2 (auto backup/restore)
				// Small dataset (≤THRESHOLD): force_sync=1 (synchronous)
				// Large dataset (>THRESHOLD): force_sync=0 (auto detect async)
				values.force_sync = total_records <= BULK_ATTENDANCE_ASYNC_THRESHOLD ? 1 : 0;
				execute_bulk_update_attendance_v2(values, employee_list, dialog, list_view);
			});
		}
	});

	dialog.show();
}

// Execute Bulk Update - Simple & Clean (Single API call)
// Now used for BOTH small and large datasets with auto backup/restore
function execute_bulk_update_attendance_v2(values, employee_list, dialog, list_view) {
	dialog.hide();

	// Setup realtime listener for background job completion
	console.log("🎧 Registered realtime listener for bulk_update_attendance_complete");

	frappe.realtime.on('bulk_update_attendance_complete', function (data) {
		console.log("📡 Received bulk_update_attendance_complete event:", data);

		if (data.success) {
			console.log("✅ Background job completed successfully, showing results");
			show_attendance_results_dialog_v2({
				type: 'success',
				result: data.result,
				background: true,
				from_date: values.from_date,
				to_date: values.to_date
			});
		} else {
			console.error("❌ Background job failed:", data.message);
			frappe.msgprint({
				title: __('Background Job Failed'),
				message: data.message || 'Operation encountered an error',
				indicator: 'red'
			});
		}

		// Cleanup listener
		frappe.realtime.off('bulk_update_attendance_complete');
		console.log("🔇 Removed realtime listener");

		// Refresh list
		if (list_view) {
			list_view.refresh();
		}
	});

	// Get the appropriate method based on configuration
	// Default to optimized version (can be changed via attendance_config.py)
	const method = "customize_erpnext.overrides.shift_type.shift_type_optimized.bulk_update_attendance_optimized";

	// Single API call - Backend auto-detects sync/async
	frappe.call({
		method: method,
		args: {
			from_date: values.from_date,
			to_date: values.to_date,
			employees: employee_list ? JSON.stringify(employee_list) : null,
			batch_size: 100,
			force_sync: values.force_sync || 0
		},
		freeze: true,
		freeze_message: __('Processing attendance update...'),
		callback: function (r) {
			console.log("📡 Bulk Update Response:", r);

			if (!r.exc && r.message && r.message.success) {
				const result = r.message;
				console.log("✅ Result data:", result);

				if (result.background_job) {
					// Large dataset - Show background job info
					console.log("🚀 Background job mode");
					show_background_job_dialog_v2({
						title: __('Background Processing Started'),
						message: result.message,
						job_id: result.job_id,
						estimated_records: result.estimated_records
					});
				} else {
					// Small dataset - Show results immediately
					console.log("⚡ Sync mode - showing results:", result.result);

					if (!result.result) {
						console.error("❌ result.result is undefined!");
						frappe.msgprint({
							title: __('Processing Complete'),
							message: __('Attendance update completed but result details are not available.'),
							indicator: 'orange'
						});
						return;
					}

					show_attendance_results_dialog_v2({
						type: 'success',
						result: result.result,
						background: false,
						from_date: values.from_date,
						to_date: values.to_date
					});

					// Refresh list
					if (list_view) {
						list_view.refresh();
					}
				}
			} else {
				console.error("❌ Error response:", r);
				frappe.msgprint({
					title: __('Error'),
					message: __('Failed to update attendance. Please check error log.'),
					indicator: 'red'
				});
			}
		},
		error: function (r) {
			console.error('Bulk update attendance error:', r);
			frappe.msgprint({
				title: __('System Error'),
				message: __('An error occurred. Please check browser console for details.'),
				indicator: 'red'
			});
		}
	});
}

// Results Dialog - Clean & Informative
function show_attendance_results_dialog_v2(options) {
	const result = options.result || {};
	const from_date = options.from_date;
	const to_date = options.to_date;
	const processing_mode = options.background ? 'Background Job' : 'Synchronous Processing';

	// Map backend fields to frontend expected fields
	const records_processed = result.actual_records || result.processed || 0;
	const total_operations = result.total_operations || 0;

	// Log all performance metrics to console for debugging
	console.log("📊 Attendance Update Performance Metrics:");
	console.log("- Processing Mode:", processing_mode);
	console.log("- Records Created/Updated:", records_processed);
	console.log("- Total Records in DB:", result.total_records_in_db || records_processed);
	console.log("- Total Operations:", total_operations);
	console.log("- Shifts Processed:", result.shifts_processed || 0);
	console.log("- Employees Total:", result.total_employees || 0);
	console.log("- Employees with Attendance:", result.employees_with_attendance || 0);
	console.log("- Employees Skipped:", result.employees_skipped || 0);
	if (result.employees_skipped > 0 && result.skipped_details) {
		console.log(`⚠️ ${result.employees_skipped} employees skipped:`, result.skipped_details);
	}
	console.log("- Days:", result.total_days || 0);
	console.log("- Date Range:", from_date, "to", to_date);
	console.log("- Processing Time:", result.processing_time || 0, "s");
	console.log("- Throughput:", result.records_per_second || 0, "records/sec");
	console.log("- Errors:", result.errors || 0);
	console.log("- Success Rate:", result.errors ? (((records_processed || 0) - result.errors) / (records_processed || 1) * 100).toFixed(1) : '100.0', "%");
	console.log("- Full result object:", result);

	// Safety checks
	if (!result || Object.keys(result).length === 0) {
		console.warn("⚠️ Empty result object, showing minimal info");
		frappe.msgprint({
			title: __('Processing Complete'),
			message: __('Attendance update completed successfully.'),
			indicator: 'green'
		});
		return;
	}

	// Log shift details to console (not shown in dialog)
	const per_shift = result.per_shift || {};

	if (per_shift && Object.keys(per_shift).length > 0) {
		console.log("\n📊 Attendance by Shift:");
		console.log("─".repeat(70));
		console.log(`${'Shift'.padEnd(20)} ${'Before'.padStart(10)} ${'After'.padStart(10)} ${'New/Updated'.padStart(15)}`);
		console.log("─".repeat(70));

		let total_before = 0;
		let total_after = 0;
		let total_new_or_updated = 0;

		for (const [shift_name, shift_data] of Object.entries(per_shift)) {
			const before = shift_data.before || 0;
			const after = shift_data.after || 0;
			const new_or_updated = shift_data.new_or_updated || 0;

			total_before += before;
			total_after += after;
			total_new_or_updated += new_or_updated;

			console.log(`${shift_name.padEnd(20)} ${String(before).padStart(10)} ${String(after).padStart(10)} ${String(new_or_updated).padStart(15)}`);
		}

		console.log("─".repeat(70));
		console.log(`${'Total'.padEnd(20)} ${String(total_before).padStart(10)} ${String(total_after).padStart(10)} ${String(total_new_or_updated).padStart(15)}`);
		console.log("─".repeat(70));
	} else {
		console.log("📊 No shift details available");
	}

	// Build employee stats message
	let employee_stats_html = '';
	if (result.employees_skipped && result.employees_skipped > 0) {
		employee_stats_html = `
			<div class="alert alert-info mt-3 mb-0">
				<strong><i class="fa fa-users"></i> ${__('Employee Summary')}:</strong>
				<div style="margin-top:4px">
					${__('Total')}: <strong>${result.total_employees}</strong>
					&nbsp;|&nbsp; ${__('With attendance')}: <strong>${result.employees_with_attendance || 0}</strong>
					&nbsp;|&nbsp; ${__('Skipped')}: <strong>${result.employees_skipped}</strong>
				</div>
			</div>
		`;
	}

	// Simple dialog showing only main results
	frappe.msgprint({
		title: __('Attendance Update Completed'),
		message: `
			<div class="alert alert-success mb-3">
				<h6 class="alert-heading">${__('Operation Completed Successfully')}</h6>
				<p class="mb-1">${__('Attendance records have been updated with latest check-in data.')}</p>
				<small class="text-muted">
					${from_date && to_date ? `<i class="fa fa-calendar"></i> ${frappe.datetime.str_to_user(from_date)} ${__('to')} ${frappe.datetime.str_to_user(to_date)}` : ''}
					${result.total_employees ? `&nbsp;&nbsp;|&nbsp;&nbsp;<i class="fa fa-users"></i> ${__("{0} employees processed", [result.total_employees])}` : ''}
				</small>
			</div>

			${employee_stats_html}

			${result.errors > 0 ? `
				<div class="alert alert-warning mt-3 mb-0">
					<i class="fa fa-exclamation-triangle"></i>
					<strong>${__('Note')}:</strong> ${__("{0} errors occurred.", [result.errors])}
					${__('Check')} <a href="/app/error-log">${__('Error Log')}</a> ${__('for details.')}</div>
			` : ''}
		`,
		indicator: 'green',
		wide: true
	});
}

// Background Job Dialog
function show_background_job_dialog_v2(options) {
	frappe.msgprint({
		title: options.title,
		message: `
			<div class="alert alert-info">
				<p class="mb-3">${options.message}</p>
				<div>
					<strong><i class="fa fa-list"></i> ${__('Records')}:</strong> ~${options.estimated_records}<br>
					<strong><i class="fa fa-clock-o"></i> ${__('Estimated time')}:</strong> ${Math.ceil(options.estimated_records / 50)} - ${Math.ceil(options.estimated_records / 30)} ${__('seconds')}<br>
					<strong><i class="fa fa-bell"></i> ${__('Notification')}:</strong> ${__("You'll be notified when complete")}
				</div>
			</div>
		`,
		indicator: 'blue'
	});
}