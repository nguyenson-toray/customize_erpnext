// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// List View customizations for Daily Timesheet
frappe.listview_settings['Daily Timesheet'] = {
	add_fields: ["employee_name", "attendance_date", "shift", "working_hours", "overtime_hours", "status"],
	
	onload: function(listview) {
		// Add bulk action buttons only for HR Manager and System Manager
		if (frappe.user.has_role('HR Manager') || frappe.user.has_role('System Manager')) {
			setTimeout(function() {
				try {
					// Combined Bulk Create, Recalculate Timesheet button  
					listview.page.add_menu_item(__("Bulk Create, Recalculate Timesheet"), function() {
						show_bulk_create_recalculate_dialog();
					});
					
					console.log('Daily Timesheet list button added successfully');
				} catch (e) {
					console.error('Failed to add Daily Timesheet buttons:', e);
				}
			}, 300);
		}
	},
	
	get_indicator: function(doc) {
		// Status indicators with color coding as requested
		if (doc.status === "Present") {
			if (doc.late_entry || doc.early_exit) {
				return [__("Present (Issues)"), "orange", "status,=,Present"];
			}
			return [__("Present"), "green", "status,=,Present"];
		} else if (doc.status === "Present + OT") {
			return [__("Present + OT"), "blue", "status,=,Present + OT"];
		} else if (doc.status === "Absent") {
			return [__("Absent"), "red", "status,=,Absent"];
		} else if (doc.status === "Half Day") {
			return [__("Half Day"), "yellow", "status,=,Half Day"];
		}
		return [__(doc.status), "gray", "status,=," + doc.status];
	}
};

// Combined Bulk Create, Recalculate Timesheet Dialog
function show_bulk_create_recalculate_dialog() {
	let dialog = new frappe.ui.Dialog({
		title: __("Bulk Create, Recalculate Timesheet"),
		size: 'large',
		fields: [
			{
				fieldtype: 'Section Break',
				label: __('Date Range Selection')
			},
			{
				fieldtype: 'Date',
				fieldname: 'from_date',
				label: __('From Date'),
				default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
				reqd: 1
			},
			{
				fieldtype: 'Column Break'
			},
			{
				fieldtype: 'Date',
				fieldname: 'to_date',
				label: __('To Date'),
				default: frappe.datetime.get_today(),
				reqd: 1
			},
			{
				fieldtype: 'Section Break',
				label: __('Filters (Optional)')
			},
			{
				fieldtype: 'Link',
				fieldname: 'employee',
				label: __('Employee (optional)'),
				options: 'Employee',
				description: __('Leave empty to process all employees')
			},
			{
				fieldtype: 'Section Break',
				label: __('Information')
			},
			{
				fieldtype: 'HTML',
				fieldname: 'info',
				options: `
					<div class="alert alert-success">
						<h6><strong>Bulk Create + Recalculate Daily Timesheet</strong></h6>
						<ul>
							<li><strong>Combined Operation:</strong> Create missing Daily Timesheet records AND recalculate existing ones</li>
							<li><strong>Process:</strong> Find all active employees → Create new timesheets OR update existing ones → Full recalculation (working hours + overtime)</li>
							<li><strong>Safe:</strong> Creates missing records, fully recalculates existing ones with latest Employee Checkin and Overtime Registration data</li>
							<li><strong>Limit:</strong> Maximum 30 days to prevent system overload</li>
							<li><strong>Comprehensive:</strong> Handles both creation and recalculation in one optimized operation</li>
						</ul>
					</div>
				`
			}
		],
		primary_action_label: __('Create & Recalculate'),
		primary_action: function(values) {
			if (!values.from_date || !values.to_date) {
				frappe.msgprint(__('Please select both From Date and To Date'));
				return;
			}
			
			if (values.from_date > values.to_date) {
				frappe.msgprint(__('From Date cannot be greater than To Date'));
				return;
			}
			
			// Check date range limit (30 days)
			if (frappe.datetime.get_diff(values.to_date, values.from_date) > 30) {
				frappe.msgprint(__('Date range too large. Maximum 30 days allowed.'));
				return;
			}
			
			frappe.confirm(
				__('Create and recalculate Daily Timesheet records for the period {0} to {1}?<br><br>This will:<br>• Create missing timesheet records<br>• Recalculate existing timesheet records<br>• Update working hours and overtime from latest data', [
					frappe.datetime.str_to_user(values.from_date),
					frappe.datetime.str_to_user(values.to_date)
				]),
				function() {
					execute_bulk_create_recalculate_hybrid(values, dialog);
				}
			);
		}
	});
	
	dialog.show();
}


// Execute Combined Bulk Create + Recalculate - HYBRID VERSION
function execute_bulk_create_recalculate_hybrid(values, dialog) {
	let progress_dialog = show_progress_dialog_hybrid(__('Creating and Recalculating Daily Timesheets...'));
	dialog.hide();
	
	// Setup progress listener
	frappe.realtime.on('progress', function(data) {
		if (progress_dialog && progress_dialog.update_progress) {
			progress_dialog.update_progress(data.progress || 0, data.title || 'Processing...', data.description || '');
		}
	});
	
	frappe.call({
		method: "customize_erpnext.customize_erpnext.doctype.daily_timesheet.daily_timesheet.bulk_create_recalculate_timesheet",
		args: {
			from_date: values.from_date,
			to_date: values.to_date,
			employee: values.employee,
			batch_size: 50  // Optimal batch size for combined operation
		},
		freeze: false,
		callback: function(r) {
			// Stop listening to progress updates
			frappe.realtime.off('progress');
			
			setTimeout(() => {
				try {
					progress_dialog.hide();
				} catch (e) {
					console.log('Progress dialog hide failed:', e);
				}
				
				if (!r.exc && r.message && r.message.success) {
					const result = r.message;
					
					// Check if this is a background job
					if (result.background_job) {
						show_background_job_dialog({
							title: __('Large Operation Queued'),
							message: result.message,
							job_id: result.job_id,
							operation_type: 'create_recalculate'
						});
					} else {
						// Regular synchronous result
						show_results_dialog_hybrid({
							title: __('Bulk Create + Recalculate Results - OPTIMIZED'),
							type: 'success',
							result: result,
							operation_type: 'create_recalculate'
						});
					}
				} else {
					frappe.msgprint({
						title: __('Error'),
						message: __('Failed to create and recalculate Daily Timesheet records. Please check the error log.'),
						indicator: 'red'
					});
				}
			}, 200);
		},
		error: function(r) {
			frappe.realtime.off('progress');
			
			setTimeout(() => {
				try {
					progress_dialog.hide();
				} catch (e) {
					console.log('Progress dialog hide failed:', e);
				}
				
				console.error('Bulk create + recalculate error:', r);
				frappe.msgprint({
					title: __('System Error'),
					message: __('An error occurred during bulk create + recalculate. Please check browser console.'),
					indicator: 'red'
				});
			}, 200);
		}
	});
}


// Progress Dialog Helper - HYBRID VERSION with Real-time Updates
function show_progress_dialog_hybrid(message = __('Processing...')) {
	let progress_dialog = new frappe.ui.Dialog({
		title: __('Processing in Progress - OPTIMIZED'),
		fields: [
			{
				fieldtype: 'HTML',
				fieldname: 'progress_html',
				options: `
					<div class="text-center" style="padding: 30px;">
						<div class="progress mb-3" style="height: 25px;">
							<div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
								 role="progressbar" 
								 id="bulk-progress-bar"
								 style="width: 0%" 
								 aria-valuenow="0" 
								 aria-valuemin="0" 
								 aria-valuemax="100">0%</div>
						</div>
						<h5 id="bulk-progress-title" style="margin-top: 20px;">${message}</h5>
						<p id="bulk-progress-description" class="text-muted">Initializing batch processing...</p>
						<div class="mt-3">
							<small class="text-info">
								⚡ Using optimized batch processing for better performance
							</small>
						</div>
					</div>
				`
			}
		],
		no_submit_on_enter: true
	});
	
	progress_dialog.show();
	
	// Update progress method
	progress_dialog.update_progress = function(progress, title, description) {
		try {
			const progressBar = document.getElementById('bulk-progress-bar');
			const progressTitle = document.getElementById('bulk-progress-title');
			const progressDescription = document.getElementById('bulk-progress-description');
			
			if (progressBar) {
				const roundedProgress = Math.round(progress);
				progressBar.style.width = roundedProgress + '%';
				progressBar.setAttribute('aria-valuenow', roundedProgress);
				progressBar.textContent = roundedProgress + '%';
				
				// Change color based on progress
				progressBar.className = 'progress-bar progress-bar-striped progress-bar-animated ';
				if (progress < 25) {
					progressBar.className += 'bg-info';
				} else if (progress < 50) {
					progressBar.className += 'bg-primary';
				} else if (progress < 75) {
					progressBar.className += 'bg-warning';
				} else {
					progressBar.className += 'bg-success';
				}
			}
			
			if (progressTitle && title) {
				progressTitle.textContent = title;
			}
			
			if (progressDescription && description) {
				progressDescription.textContent = description;
			}
		} catch (e) {
			console.log('Progress update error:', e);
		}
	};
	
	// Force close method
	progress_dialog.force_close = function() {
		try {
			if (progress_dialog.$wrapper && progress_dialog.$wrapper.length) {
				progress_dialog.$wrapper.modal('hide');
				progress_dialog.$wrapper.remove();
			}
			if (progress_dialog.display) {
				progress_dialog.display = false;
			}
			// Remove modal backdrop if exists
			$('.modal-backdrop').remove();
			// Remove modal-open class from body
			$('body').removeClass('modal-open');
			// Reset body padding
			$('body').css('padding-right', '');
		} catch (e) {
			console.log('Dialog force close error:', e);
		}
	};
	
	return progress_dialog;
}

// Results Dialog Helper - HYBRID VERSION with Performance Stats
function show_results_dialog_hybrid(options) {
	const result = options.result;
	let alert_class = options.type === 'success' ? 'alert-success' : 'alert-danger';
	let indicator_class = options.type === 'success' ? 'green' : 'red';
	
	let performance_stats = '';
	if (result && options.type === 'success') {
		const throughput = result.records_per_second || 0;
		const efficiency = result.errors ? ((result.processed || result.created + result.updated) / (result.total || result.total_operations) * 100).toFixed(1) : '100';
		
		if (options.operation_type === 'create') {
			performance_stats = `
				<div class="mt-3 p-3" style="background-color: #f8f9fa; border-radius: 8px;">
					<h6 class="text-success mb-2">📊 Performance Summary</h6>
					<div class="row">
						<div class="col-md-6">
							<strong>Created:</strong> ${result.created || 0} records<br>
							<strong>Updated:</strong> ${result.updated || 0} records<br>
							<strong>Errors:</strong> ${result.errors || 0} records
						</div>
						<div class="col-md-6">
							<strong>Processing Time:</strong> ${result.processing_time || 0}s<br>
							<strong>Throughput:</strong> ${throughput.toFixed(1)} records/sec<br>
							<strong>Success Rate:</strong> ${efficiency}%
						</div>
					</div>
					<div class="mt-2">
						<small class="text-info">⚡ Optimized with batch processing (${result.total_operations} operations)</small>
					</div>
				</div>
			`;
		} else if (options.operation_type === 'create_recalculate') {
			performance_stats = `
				<div class="mt-3 p-3" style="background-color: #f8f9fa; border-radius: 8px;">
					<h6 class="text-success mb-2">📊 Combined Operation Performance</h6>
					<div class="row">
						<div class="col-md-6">
							<strong>Created:</strong> ${result.created || 0} records<br>
							<strong>Recalculated:</strong> ${result.updated || 0} records<br>
							<strong>Errors:</strong> ${result.errors || 0} records
						</div>
						<div class="col-md-6">
							<strong>Processing Time:</strong> ${result.processing_time || 0}s<br>
							<strong>Throughput:</strong> ${throughput.toFixed(1)} records/sec<br>
							<strong>Success Rate:</strong> ${efficiency}%
						</div>
					</div>
					<div class="mt-2">
						<small class="text-success">✅ Combined create + recalculate operation (${result.total_operations} total operations)</small>
					</div>
				</div>
			`;
		} else if (options.operation_type === 'recalculate') {
			performance_stats = `
				<div class="mt-3 p-3" style="background-color: #f8f9fa; border-radius: 8px;">
					<h6 class="text-success mb-2">📊 Performance Summary</h6>
					<div class="row">
						<div class="col-md-6">
							<strong>Processed:</strong> ${result.processed || 0} records<br>
							<strong>Total:</strong> ${result.total || 0} records<br>
							<strong>Errors:</strong> ${result.errors || 0} records
						</div>
						<div class="col-md-6">
							<strong>Processing Time:</strong> ${result.processing_time || 0}s<br>
							<strong>Throughput:</strong> ${throughput.toFixed(1)} records/sec<br>
							<strong>Success Rate:</strong> ${efficiency}%
						</div>
					</div>
					<div class="mt-2">
						<small class="text-info">⚡ Optimized with smart batching (${result.total} records processed)</small>
					</div>
				</div>
			`;
		}
	}
	
	frappe.msgprint({
		title: options.title,
		message: `
			<div class="alert ${alert_class}">
				<h6 class="alert-heading">✅ Operation Completed Successfully!</h6>
				${options.operation_type === 'create' ? 
					`Bulk creation completed with optimized batch processing.` : 
					options.operation_type === 'create_recalculate' ?
					`Combined bulk create + recalculate completed with optimized processing.` :
					`Bulk recalculation completed with smart batching.`
				}
			</div>
			${performance_stats}
		`,
		indicator: indicator_class,
		wide: true
	});
	
	// Refresh list view
	setTimeout(function() {
		if (cur_list && cur_list.doctype === 'Daily Timesheet') {
			cur_list.refresh();
		}
	}, 1000);
}

// Background Job Dialog Helper
function show_background_job_dialog(options) {
	// Setup listener for background job completion
	frappe.realtime.on('bulk_operation_complete', function(data) {
		if (data.success) {
			let title = '';
			if (data.operation === 'create') {
				title = 'Background Creation Completed';
			} else if (data.operation === 'create_recalculate') {
				title = 'Background Create + Recalculate Completed';
			} else {
				title = 'Background Recalculation Completed';
			}
			
			show_results_dialog_hybrid({
				title: __(title),
				type: 'success',
				result: data.result,
				operation_type: data.operation
			});
		} else {
			frappe.msgprint({
				title: __('Background Operation Failed'),
				message: data.message || 'Background operation encountered an error',
				indicator: 'red'
			});
		}
		
		// Remove the listener after handling the event
		frappe.realtime.off('bulk_operation_complete');
	});
	
	frappe.msgprint({
		title: options.title,
		message: `
			<div class="alert alert-info">
				<h6 class="alert-heading">🚀 Background Processing Started</h6>
				<p>${options.message}</p>
				<hr>
				<div class="mt-3 p-3" style="background-color: #f8f9fa; border-radius: 8px;">
					<h6 class="text-primary mb-2">📋 What happens next?</h6>
					<ul class="mb-0">
						<li><strong>Background Processing:</strong> Operation is running in the background to prevent timeouts</li>
						<li><strong>Auto-notification:</strong> You'll be notified when the operation completes</li>
						<li><strong>Continue Working:</strong> You can continue using the system normally</li>
						<li><strong>Job ID:</strong> <code>${options.job_id}</code></li>
					</ul>
				</div>
			</div>
		`,
		indicator: 'blue',
		wide: true
	});
}