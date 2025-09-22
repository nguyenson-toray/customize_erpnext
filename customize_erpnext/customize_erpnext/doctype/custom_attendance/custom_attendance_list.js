// Enhanced List View customizations với Overtime Bulk Operations
frappe.listview_settings['Custom Attendance'] = {
  add_fields: ['status', 'working_hours', 'overtime_hours', 'auto_sync_enabled', 'docstatus'],
  onload: function (listview) {

    // Add Bulk Create button cho HR Manager và System Manager
    if (frappe.user.has_role('HR Manager') || frappe.user.has_role('System Manager')) {
      setTimeout(function () {
        try {
          // Existing bulk operations
          listview.page.add_menu_item(__('Bulk Create from Shift Date'), function () {
            show_bulk_process_dialog();
          });

          listview.page.add_menu_item(__('Daily Attendance Completion'), function () {
            show_daily_completion_dialog();
          });

          listview.page.add_menu_item(__('Check Missing Attendance'), function () {
            show_missing_attendance_dialog();
          });

          // NEW: Overtime bulk operations
          listview.page.add_menu_item(__('Bulk Recalculate Overtime'), function () {
            show_bulk_overtime_recalculate_dialog();
          });
          
          
          console.log('Enhanced Custom Attendance buttons with overtime added successfully');

              listview.page.add_menu_item(__('Update Shifts from Registration'), function() {
                  show_bulk_update_dialog(listview);
              });
        
              // Thêm button "Check Updateable Records"
              listview.page.add_menu_item(__('Check Updateable Records'), function() {
                  show_updateable_records_dialog();
              });
        } catch (e) {
          console.error('Failed to add enhanced buttons:', e);
        }
      }, 300);
    }
  },
  get_indicator: function (doc) {
    if (doc.docstatus === 1) {
      if (doc.status === 'Present') {
        // Show different indicator if has overtime
        if (doc.overtime_hours && doc.overtime_hours > 0) {
          return [__('Present + OT'), 'blue', 'status,=,Present'];
        }
        return [__('Present'), 'green', 'status,=,Present'];
      } else if (doc.status === 'Absent') {
        return [__('Absent'), 'red', 'status,=,Absent'];
      } else if (doc.status === 'Half Day') {
        return [__('Half Day'), 'orange', 'status,=,Half Day'];
      } else if (doc.status === 'Work From Home') {
        return [__('Work From Home'), 'purple', 'status,=,Work From Home'];
      } else if (doc.status === 'On Leave') {
        return [__('On Leave'), 'dark-grey', 'status,=,On Leave'];
      }
    } else if (doc.docstatus === 0) {
      if (doc.status === 'Present') {
        // Show different indicator if has overtime
        if (doc.overtime_hours && doc.overtime_hours > 0) {
          return [__('Present + OT'), 'blue', 'status,=,Present'];
        }
        return [__('Present'), 'green', 'status,=,Present'];
      } else if (doc.status === 'Absent') {
        return [__('Absent'), 'red', 'status,=,Absent'];
      } else if (doc.status === 'Half Day') {
        return [__('Half Day'), 'orange', 'status,=,Half Day'];
      } else if (doc.status === 'Work From Home') {
        return [__('Work From Home'), 'blue', 'status,=,Work From Home'];
      } else if (doc.status === 'On Leave') {
        return [__('On Leave'), 'purple', 'status,=,On Leave'];
      }
    } else if (doc.docstatus === 2) {
      return [__('Cancelled'), 'red', 'docstatus,=,2'];
    }

    return [__('Draft'), 'grey', 'docstatus,=,0'];
  }
};

// NEW: Bulk Overtime Recalculate Dialog
function show_bulk_overtime_recalculate_dialog() {
  let dialog = new frappe.ui.Dialog({
    title: __('Bulk Recalculate Overtime'),
    size: 'large',
    fields: [
      {
        fieldtype: 'Section Break',
        label: __('Date Range for Overtime Recalculation')
      },
      {
        fieldtype: 'Date',
        fieldname: 'start_date',
        label: __('From Date'),
        default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
        reqd: 1
      },
      {
        fieldtype: 'Column Break'
      },
      {
        fieldtype: 'Date',
        fieldname: 'end_date',
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
        label: __('Specific Employee'),
        options: 'Employee',
        description: __('Leave empty to process all employees')
      },
      {
        fieldtype: 'Column Break'
      },
      {
        fieldtype: 'Link',
        fieldname: 'shift',
        label: __('Specific Shift'),
        options: 'Shift Type',
        description: __('Leave empty to process all shifts')
      },
      {
        fieldtype: 'Section Break',
        label: __('Options')
      },
      {
        fieldtype: 'Check',
        fieldname: 'only_with_checkins',
        label: __('Only records with check-in/out'),
        default: 1,
        description: __('Process only attendance records that have both check-in and check-out times')
      },
      {
        fieldtype: 'Check',
        fieldname: 'draft_only',
        label: __('Draft records only'),
        default: 1,
        description: __('Process only draft (unsubmitted) attendance records')
      },
      {
        fieldtype: 'Section Break',
        label: __('Information')
      },
      {
        fieldtype: 'HTML',
        fieldname: 'info',
        options: `
          <div class="alert alert-warning">
            <h6><strong>Bulk Overtime Recalculation</strong></h6>
            <ul>
              <li><strong>Purpose:</strong> Recalculate working hours including overtime from approved Overtime Requests</li>
              <li><strong>Logic:</strong> 
                <ul>
                  <li>Find all approved Overtime Requests in the date range</li>
                  <li>Recalculate attendance working hours including overtime hours</li>
                  <li>Update working_hours field with total (regular + overtime)</li>
                </ul>
              </li>
              <li><strong>Safe:</strong> Only updates existing attendance records, no new records created</li>
              <li><strong>Reversible:</strong> You can always recalculate again if overtime requests change</li>
            </ul>
          </div>
        `
      }
    ],
    primary_action_label: __('Start Recalculation'),
    primary_action: function (values) {
      start_bulk_overtime_recalculation(values, dialog);
    }
  });

  dialog.show();
}

function start_bulk_overtime_recalculation(values, dialog) {
  if (!values.start_date || !values.end_date) {
    frappe.msgprint(__('Please select both start and end dates'));
    return;
  }

  if (frappe.datetime.get_diff(values.end_date, values.start_date) > 90) {
    frappe.msgprint(__('Date range too large. Maximum 90 days allowed.'));
    return;
  }

  frappe.confirm(
    __('Recalculate overtime for attendance records from {0} to {1}?<br><br>This will update working hours for all matching records.', [
      frappe.datetime.str_to_user(values.start_date),
      frappe.datetime.str_to_user(values.end_date)
    ]),
    function () {
      let progress_dialog = show_progress_dialog('Recalculating overtime...');
      dialog.hide();

      frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.api_bulk_recalculate_overtime',
        args: {
          date_from: values.start_date,
          date_to: values.end_date,
          employee: values.employee || null,
          shift: values.shift || null,
          only_with_checkins: values.only_with_checkins || false,
          draft_only: values.draft_only || false
        },
        freeze: false,
        callback: function (r) {
          progress_dialog.hide();

          if (r && r.message && r.message.success) {
            show_overtime_recalc_results_dialog(r.message);
          } else {
            frappe.msgprint(__('Bulk Overtime Recalculation Error: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
          }
        },
        error: function (r) {
          progress_dialog.hide();
          console.error('Bulk overtime recalc error:', r);
          frappe.msgprint(__('System Error: Please check error logs'));
        }
      });
    }
  );
}

function show_overtime_recalc_results_dialog(results) {
  let status_class = results.error_count === 0 ? 'alert-success' : 'alert-warning';

  let html = `
    <div class="${status_class} alert">
      <h5>Bulk Overtime Recalculation Results</h5>
      <div class="row">
        <div class="col-md-4">
          <p><strong>Records Processed:</strong> ${results.success_count}</p>
        </div>
        <div class="col-md-4">
          <p><strong>With Overtime Found:</strong> ${results.overtime_found_count}</p>
        </div>
        <div class="col-md-4">
          <p><strong>Errors:</strong> ${results.error_count}</p>
        </div>
      </div>
    </div>
  `;

  if (results.overtime_found_count > 0) {
    html += `
      <div class="alert alert-info">
        <strong>Success!</strong> ${results.overtime_found_count} attendance records were updated with overtime hours.
        Check the individual records to see the updated working hours.
      </div>
    `;
  }

  if (results.error_count > 0) {
    html += `
      <div class="alert alert-warning">
        <strong>Partial Success:</strong> ${results.error_count} records encountered errors during processing.
        Check the error logs for details.
      </div>
    `;
  }

  let results_dialog = new frappe.ui.Dialog({
    title: __('Overtime Recalculation Results'),
    size: 'large',
    fields: [
      {
        fieldtype: 'HTML',
        fieldname: 'results_html',
        options: html
      }
    ],
    primary_action_label: __('Close'),
    primary_action: function () {
      results_dialog.hide();

      // Refresh current list view
      if (cur_list && cur_list.doctype === 'Custom Attendance') {
        cur_list.refresh();
      }
    }
  });

  results_dialog.show();
}

// EXISTING functions (keeping all previous functionality)
function show_bulk_process_dialog() {
  let dialog = new frappe.ui.Dialog({
    title: __('Bulk Create Custom Attendance'),
    size: 'large',
    fields: [
      {
        fieldtype: 'Section Break',
        label: __('Date Range Selection')
      },
      {
        fieldtype: 'Link',
        fieldname: 'shift_type',
        label: __('Shift Type (Optional)'),
        options: 'Shift Type',
        description: __('Leave empty to process all shifts. If selected, will use "Process Attendance After" date from this shift.')
      },
      {
        fieldtype: 'Column Break'
      },
      {
        fieldtype: 'Check',
        fieldname: 'use_shift_date',
        label: __('Use Shift "Process Attendance After" Date'),
        default: 1,
        description: __('Use the date from shift settings as start date')
      },
      {
        fieldtype: 'Section Break',
        label: __('Custom Date Range'),
        depends_on: 'eval:!doc.use_shift_date'
      },
      {
        fieldtype: 'Date',
        fieldname: 'start_date',
        label: __('Start Date'),
        default: frappe.datetime.add_days(frappe.datetime.get_today(), -30),
        mandatory_depends_on: 'eval:!doc.use_shift_date'
      },
      {
        fieldtype: 'Column Break'
      },
      {
        fieldtype: 'Date',
        fieldname: 'end_date',
        label: __('End Date'),
        default: frappe.datetime.get_today(),
        reqd: 1
      },
      {
        fieldtype: 'Section Break',
        label: __('Preview')
      },
      {
        fieldtype: 'Button',
        fieldname: 'preview_btn',
        label: __('Preview Data'),
        click: function () {
          show_preview(dialog);
        }
      },
      {
        fieldtype: 'HTML',
        fieldname: 'preview_html',
        label: __('Preview Results')
      },
      {
        fieldtype: 'Section Break',
        label: __('Information')
      },
      {
        fieldtype: 'HTML',
        fieldname: 'info',
        options: `
          <div class="alert alert-info">
            <h6><strong>Bulk Create Custom Attendance</strong></h6>
            <ul>
              <li><strong>Purpose:</strong> Create Custom Attendance records for employees with check-ins</li>
              <li><strong>Date Range:</strong> Maximum 90 days to prevent system overload</li>
              <li><strong>Process:</strong> Create attendance → Auto sync from check-ins → Calculate overtime → Report results</li>
              <li><strong>Skip:</strong> Employees already having Custom Attendance records</li>
              <li><strong>Safe:</strong> No duplicates will be created</li>
            </ul>
          </div>
        `
      }
    ],
    primary_action_label: __('Start Bulk Process'),
    primary_action: function (values) {
      start_bulk_process(values, dialog);
    }
  });

  dialog.show();
}

// Progress dialog helper
function show_progress_dialog(message = 'Processing...') {
  let progress_dialog = new frappe.ui.Dialog({
    title: __('Processing in Progress'),
    fields: [
      {
        fieldtype: 'HTML',
        fieldname: 'progress_html',
        options: `
          <div class="text-center" style="padding: 30px;">
            <div class="spinner-border text-primary" role="status">
              <span class="sr-only">Processing...</span>
            </div>
            <h5 style="margin-top: 20px;">${message}</h5>
            <p class="text-muted">This may take several minutes. Please wait...</p>
          </div>
        `
      }
    ]
  });

  progress_dialog.show();
  return progress_dialog;
}

// Daily completion dialog
function show_daily_completion_dialog() {
  let dialog = new frappe.ui.Dialog({
    title: __('Daily Attendance Completion'),
    size: 'large',
    fields: [
      {
        fieldtype: 'Section Break',
        label: __('Daily Completion Options')
      },
      {
        fieldtype: 'Select',
        fieldname: 'completion_type',
        label: __('Completion Type'),
        options: 'Single Date\nDate Range',
        default: 'Single Date',
        onchange: function () {
          dialog.layout.refresh();
        }
      },
      {
        fieldtype: 'Section Break',
        fieldname: 'single_date_section',
        label: __('Single Date Completion'),
        depends_on: 'eval:doc.completion_type=="Single Date"'
      },
      {
        fieldtype: 'Date',
        fieldname: 'target_date',
        label: __('Target Date'),
        default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
        description: __('Create attendance for all active employees on this date'),
        depends_on: 'eval:doc.completion_type=="Single Date"'
      },
      {
        fieldtype: 'Section Break',
        fieldname: 'date_range_section',
        label: __('Date Range Completion'),
        depends_on: 'eval:doc.completion_type=="Date Range"'
      },
      {
        fieldtype: 'Date',
        fieldname: 'start_date_range',
        label: __('Start Date'),
        default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
        depends_on: 'eval:doc.completion_type=="Date Range"'
      },
      {
        fieldtype: 'Column Break'
      },
      {
        fieldtype: 'Date',
        fieldname: 'end_date_range',
        label: __('End Date'),
        default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
        depends_on: 'eval:doc.completion_type=="Date Range"'
      },
      {
        fieldtype: 'Section Break',
        label: __('Preview & Summary')
      },
      {
        fieldtype: 'Button',
        fieldname: 'check_summary_btn',
        label: __('Check Summary'),
        click: function () {
          check_attendance_summary(dialog);
        }
      },
      {
        fieldtype: 'HTML',
        fieldname: 'summary_html',
        label: __('Summary Results')
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
            <h6><strong>Daily Attendance Completion</strong></h6>
            <ul>
              <li><strong>Purpose:</strong> Create attendance records for ALL active employees (including Absent)</li>
              <li><strong>Logic:</strong> Employees with check-ins become Present, Employees without check-ins become Absent</li>
              <li><strong>Overtime:</strong> Working hours will automatically include overtime from approved Overtime Requests</li>
              <li><strong>Safe:</strong> Only creates missing records, won't duplicate existing ones</li>
              <li><strong>Comprehensive:</strong> Ensures no employee is missing from attendance tracking</li>
              <li><strong>Limit:</strong> Maximum 30 days for bulk processing</li>
            </ul>
          </div>
        `
      }
    ],
    primary_action_label: __('Start Completion'),
    primary_action: function (values) {
      start_daily_completion(values, dialog);
    }
  });

  dialog.show();
}

function show_missing_attendance_dialog() {
  let dialog = new frappe.ui.Dialog({
    title: __('Check Missing Attendance'),
    size: 'large',
    fields: [
      {
        fieldtype: 'Date',
        fieldname: 'check_date',
        label: __('Check Date'),
        default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
        reqd: 1
      },
      {
        fieldtype: 'Button',
        fieldname: 'check_missing_btn',
        label: __('Check Missing Attendance'),
        click: function () {
          check_missing_attendance(dialog);
        }
      },
      {
        fieldtype: 'HTML',
        fieldname: 'missing_results_html',
        label: __('Missing Attendance Results')
      }
    ],
    primary_action_label: __('Create Missing Records'),
    primary_action: function (values) {
      create_missing_attendance(values, dialog);
    }
  });

  dialog.show();
}

// Stub functions for existing functionality - implement as needed
function show_preview(dialog) {
  let values = dialog.get_values();

  if (!values.end_date) {
    frappe.msgprint(__('Please select End Date'));
    return;
  }

  let args = {
    end_date: values.end_date
  };

  if (values.shift_type) {
    args.shift_name = values.shift_type;
  }

  if (!values.use_shift_date && values.start_date) {
    args.start_date = values.start_date;
  }

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.get_bulk_process_preview',
    args: args,
    callback: function (r) {
      if (r && r.message && r.message.success) {
        render_preview_html(dialog, r.message);
      } else {
        frappe.msgprint(__('Error getting preview: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
      }
    },
    error: function (r) {
      console.error('Preview call error:', r);
      frappe.msgprint(__('Failed to get preview. Please check console for details.'));
    }
  });
}
function start_bulk_process(values, dialog) {
  if (!values.end_date) {
    frappe.msgprint(__('Please select End Date'));
    return;
  }

  frappe.confirm(
    __('Are you sure you want to start bulk processing? This may take several minutes for large date ranges.'),
    function () {
      let args = {
        end_date: values.end_date
      };

      if (values.shift_type) {
        args.shift_name = values.shift_type;
      }

      if (!values.use_shift_date && values.start_date) {
        args.start_date = values.start_date;
      }

      let progress_dialog = show_progress_dialog();
      dialog.hide();

      frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.api_bulk_process_from_shift_date',
        args: args,
        freeze: false,
        callback: function (r) {
          progress_dialog.hide();

          if (r && r.message && r.message.success) {
            show_results_dialog(r.message);
          } else {
            frappe.msgprint(__('Bulk Process Error: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
          }
        },
        error: function (r) {
          progress_dialog.hide();
          console.error('Bulk process call error:', r);
          frappe.msgprint(__('System Error: Please check error logs'));
        }
      });
    }
  );
}
function check_attendance_summary(dialog) {
  let values = dialog.get_values();
  let completion_type = values.completion_type || 'Single Date';

  if (completion_type === 'Single Date') {
    let target_date = values.target_date;
    if (!target_date) {
      frappe.msgprint(__('Please select a target date'));
      return;
    }

    frappe.call({
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.api_get_attendance_summary_for_date',
      args: { date: target_date },
      callback: function (r) {
        if (r && r.message && r.message.success) {
          render_summary_html(dialog, r.message);
        } else {
          frappe.msgprint(__('Error getting summary: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
        }
      },
      error: function (r) {
        console.error('Summary call error:', r);
        frappe.msgprint(__('Failed to get summary. Please check console for details.'));
      }
    });
  } else {
    // Date Range mode
    let start_date = values.start_date_range;
    let end_date = values.end_date_range;

    if (!start_date || !end_date) {
      frappe.msgprint(__('Please select both start and end dates'));
      return;
    }

    frappe.call({
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.api_get_attendance_summary_for_range',
      args: {

        
        start_date: start_date,
        end_date: end_date
      },
      callback: function (r) {
        if (r && r.message && r.message.success) {
          render_range_summary_html(dialog, r.message);
        } else {
          frappe.msgprint(__('Error getting range summary: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
        }
      },
      error: function (r) {
        console.error('Range summary call error:', r);
        frappe.msgprint(__('Failed to get range summary. Please check console for details.'));
      }
    });
  }
}

function render_summary_html(dialog, data) {
  let html = `
    <div class="summary-results" style="margin-top: 15px;">
      <div class="alert alert-info">
        <h6><strong>Attendance Summary for ${frappe.datetime.str_to_user(data.date)}</strong></h6>
        <div class="row">
          <div class="col-md-6">
            <p><strong>Total Active Employees:</strong> ${data.total_employees}</p>
            <p><strong>Attendance Records:</strong> ${data.total_attendance_records}</p>
            <p><strong>Missing Records:</strong> <span class="badge badge-warning">${data.missing_attendance}</span></p>
          </div>
          <div class="col-md-6">
            <p><strong>Employees with Check-ins:</strong> ${data.employees_with_checkins}</p>
            <p><strong>Completion Rate:</strong> ${((data.total_attendance_records / data.total_employees) * 100).toFixed(1)}%</p>
          </div>
        </div>
      </div>
  `;

  if (data.attendance_breakdown && data.attendance_breakdown.length > 0) {
    html += `
      <div class="table-responsive">
        <table class="table table-bordered table-sm">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th>Status</th>
              <th>Count</th>
              <th>Percentage</th>
            </tr>
          </thead>
          <tbody>
    `;

    data.attendance_breakdown.forEach(function (row) {
      let percentage = ((row.count / data.total_attendance_records) * 100).toFixed(1);
      let badgeClass = row.status === 'Present' ? 'badge-success' :
        row.status === 'Absent' ? 'badge-danger' : 'badge-secondary';

      html += `
        <tr>
          <td><span class="badge ${badgeClass}">${row.status}</span></td>
          <td>${row.count}</td>
          <td>${percentage}%</td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;
  }

  if (data.missing_attendance > 0) {
    html += `
      <div class="alert alert-warning">
        <strong>Action Needed:</strong> ${data.missing_attendance} employees are missing attendance records.
        Click "Start Completion" to create these missing records.
      </div>
    `;
  } else {
    html += `
      <div class="alert alert-success">
        <strong>Complete:</strong> All active employees have attendance records for this date.
      </div>
    `;
  }

  html += '</div>';

  dialog.set_df_property('summary_html', 'options', html);
}

function execute_single_date_completion(date, dialog) {
  let progress_dialog = show_progress_dialog();
  dialog.hide();

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.api_manual_daily_completion',
    args: { date: date },
    freeze: false,
    callback: function (r) {
      progress_dialog.hide();

      if (r && r.message && r.message.success) {
        show_completion_results_dialog(r.message);
      } else {
        frappe.msgprint(__('Daily Completion Error: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
      }
    },
    error: function (r) {
      progress_dialog.hide();
      console.error('Single date completion call error:', r);
      frappe.msgprint(__('System Error: Please check error logs'));
    }
  });
}

// NEW: Show completion results
function show_completion_results_dialog(results) {
  let status_class = results.error_count === 0 ? 'alert-success' : 'alert-warning';

  let html = `
    <div class="${status_class} alert">
      <h5>Daily Attendance Completion - ${frappe.datetime.str_to_user(results.date)}</h5>
      <div class="row">
        <div class="col-md-6">
          <p><strong>Total Employees:</strong> ${results.total_employees}</p>
          <p><strong>Records Created:</strong> ${results.created_count}</p>
        </div>
        <div class="col-md-6">
          <p><strong>Records Updated:</strong> ${results.updated_count}</p>
          <p><strong>Errors:</strong> ${results.error_count}</p>
        </div>
      </div>
    </div>
  `;

  // Add error details if any
  if (results.errors && results.errors.length > 0) {
    html += `
      <h6 style="margin-top: 15px;">Error Details:</h6>
      <div style="max-height: 150px; overflow-y: auto; background-color: #f8f9fa; padding: 10px; border-radius: 4px;">
    `;

    results.errors.forEach(function (error) {
      html += `<small class="text-danger">• ${error}</small><br>`;
    });

    html += '</div>';
  }

  let results_dialog = new frappe.ui.Dialog({
    title: __('Daily Completion Results'),
    size: 'large',
    fields: [
      {
        fieldtype: 'HTML',
        fieldname: 'results_html',
        options: html
      }
    ],
    primary_action_label: __('Close'),
    primary_action: function () {
      results_dialog.hide();

      // Refresh current list view
      if (cur_list && cur_list.doctype === 'Custom Attendance') {
        cur_list.refresh();
      }
    }
  });

  results_dialog.show();
}


function check_missing_attendance(dialog) {
  let values = dialog.get_values();

  if (!values.check_date) {
    frappe.msgprint(__('Please select a date'));
    return;
  }

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.identify_missing_attendance',
    args: { date: values.check_date },
    callback: function (r) {
      if (r && r.message && r.message.success) {
        render_missing_attendance_html(dialog, r.message);
      } else {
        frappe.msgprint(__('Error checking missing attendance: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
      }
    },
    error: function (r) {
      console.error('Missing attendance call error:', r);
      frappe.msgprint(__('Failed to check missing attendance. Please check console for details.'));
    }
  });
}

function create_missing_attendance(values, dialog) {
  if (!values.check_date) {
    frappe.msgprint(__('Please select a date'));
    return;
  }

  frappe.confirm(
    __('Create attendance records for all missing employees on this date?'),
    function () {
      let progress_dialog = show_progress_dialog();
      dialog.hide();

      frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.api_manual_daily_completion',
        args: { date: values.check_date },
        freeze: false,
        callback: function (r) {
          progress_dialog.hide();

          if (r && r.message && r.message.success) {
            show_completion_results_dialog(r.message);
          } else {
            frappe.msgprint(__('Daily Completion Error: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
          }
        },
        error: function (r) {
          progress_dialog.hide();
          console.error('Daily completion call error:', r);
          frappe.msgprint(__('System Error: Please check error logs'));
        }
      });
    }
  );
}

// NEW: Start daily completion
function start_daily_completion(values, dialog) {
  let completion_type = values.completion_type;

  if (completion_type === 'Single Date') {
    if (!values.target_date) {
      frappe.msgprint(__('Please select a target date'));
      return;
    }

    frappe.confirm(
      __('Create attendance records for all active employees on {0}?', [frappe.datetime.str_to_user(values.target_date)]),
      function () {
        execute_single_date_completion(values.target_date, dialog);
      }
    );
  } else {
    if (!values.start_date_range || !values.end_date_range) {
      frappe.msgprint(__('Please select both start and end dates'));
      return;
    }

    frappe.confirm(
      __('Create attendance records for the date range {0} to {1}?', [
        frappe.datetime.str_to_user(values.start_date_range),
        frappe.datetime.str_to_user(values.end_date_range)
      ]),
      function () {
        execute_date_range_completion(values.start_date_range, values.end_date_range, dialog);
      }
    );
  }
}




/* Render HTML for missing attendance results */
function render_missing_attendance_html(dialog, data) {
  let html = `
    <div class="missing-results" style="margin-top: 15px;">
      <div class="alert ${data.missing_count > 0 ? 'alert-warning' : 'alert-success'}">
        <h6><strong>Missing Attendance for ${frappe.datetime.str_to_user(data.date)}</strong></h6>
        <p><strong>Missing Records:</strong> ${data.missing_count}</p>
      </div>
  `;

  if (data.missing_count > 0) {
    html += `
      <div class="table-responsive" style="max-height: 400px; overflow-y: auto;">
        <table class="table table-bordered table-sm">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th>Employee</th>
              <th>Employee Name</th>
              <th>Department</th>
              <th>Shift</th>
              <th>Check-in Status</th>
            </tr>
          </thead>
          <tbody>
    `;

    data.missing_employees.forEach(function (emp) {
      let checkinBadge = emp.checkin_status === 'Has Check-ins' ?
        '<span class="badge badge-success">Has Check-ins</span>' :
        '<span class="badge badge-secondary">No Check-ins</span>';

      html += `
        <tr>
          <td>${emp.employee}</td>
          <td>${emp.employee_name}</td>
          <td>${emp.department || '-'}</td>
          <td>${emp.default_shift || '-'}</td>
          <td>${checkinBadge}</td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;
  } else {
    html += `
      <div class="alert alert-success">
        <strong>Perfect!</strong> All active employees have attendance records for this date.
      </div>
    `;
  }

  html += '</div>';

  dialog.set_df_property('missing_results_html', 'options', html);
}


// show update Shift from Registration dialog:
// 2. DIALOG ĐỂ BULK UPDATE
function show_bulk_update_dialog(listview) {
    let dialog = new frappe.ui.Dialog({
        title: __('Bulk Update Attendance Shifts'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'description',
                options: `
                    <div class="alert alert-info">
                        <strong>Bulk Update Shifts</strong><br>
                        This will update shift and recalculate working hours for submitted attendance records 
                        that have newer shift registrations.
                    </div>
                `
            },
            {
                fieldtype: 'Link',
                fieldname: 'employee',
                label: 'Employee (Optional)',
                options: 'Employee'
            },
            {
                fieldtype: 'Date',
                fieldname: 'from_date',
                label: 'From Date'
            },
            {
                fieldtype: 'Date', 
                fieldname: 'to_date',
                label: 'To Date'
            },
            {
                fieldtype: 'Check',
                fieldname: 'preview_mode',
                label: 'Preview Only (Show records that will be updated)',
                default: 1
            }
        ],
        primary_action_label: __('Process'),
        primary_action: function(values) {
            if (values.preview_mode) {
                preview_updateable_records(values, dialog);
            } else {
                execute_bulk_update(values, dialog);
            }
        }
    });
    
    dialog.show();
}

// 3. PREVIEW RECORDS CẦN UPDATE
function preview_updateable_records(filters, dialog) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.get_attendance_records_for_update',
        args: {
            employee: filters.employee,
            from_date: filters.from_date,
            to_date: filters.to_date
        },
        freeze: true,
        freeze_message: __('Checking records...'),
        callback: function(r) {
            if (r.message && r.message.success) {
                let data = r.message;
                show_preview_results(data.records, data.updateable_count, dialog);
            } else {
                frappe.msgprint(__('Error: ') + (r.message ? r.message.message : 'Unknown error'));
            }
        }
    });
}

// 4. HIỂN THỊ PREVIEW RESULTS
function show_preview_results(records, updateable_count, parent_dialog) {
    let html = `
        <div class="preview-results">
            <h4>Preview Results</h4>
            <p><strong>Total Records:</strong> ${records.length}</p>
            <p><strong>Can Update:</strong> ${updateable_count}</p>
            
            <table class="table table-bordered">
                <thead>
                    <tr>
                        <th>Employee</th>
                        <th>Date</th>
                        <th>Current Shift</th>
                        <th>Registered Shift</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    records.forEach(function(record) {
        let statusClass = record.can_update ? 'text-success' : 'text-muted';
        let statusText = record.can_update ? 'Will Update' : 'No Change';
        
        html += `
            <tr>
                <td>${record.employee_name || record.employee}</td>
                <td>${record.attendance_date}</td>
                <td>${record.shift || 'None'}</td>
                <td>${record.registered_shift || 'None'}</td>
                <td class="${statusClass}">${statusText}</td>
            </tr>
        `;
    });
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    let preview_dialog = new frappe.ui.Dialog({
        title: __('Preview: Records to Update'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'preview_html',
                options: html
            }
        ],
        primary_action_label: updateable_count > 0 ? __('Proceed with Update') : __('Close'),
        primary_action: function() {
            if (updateable_count > 0) {
                preview_dialog.hide();
                parent_dialog.set_value('preview_mode', 0);
                parent_dialog.$wrapper.find('.btn-primary').click();
            } else {
                preview_dialog.hide();
            }
        },
        secondary_action_label: __('Back'),
        secondary_action: function() {
            preview_dialog.hide();
        }
    });
    
    preview_dialog.show();
}

// 5. EXECUTE BULK UPDATE
function execute_bulk_update(filters, dialog) {
    frappe.confirm(__('Are you sure you want to update attendance records? This action cannot be undone.'), function() {
        
        let update_filters = {
            docstatus: 1
        };
        
        if (filters.employee) {
            update_filters.employee = filters.employee;
        }
        
        if (filters.from_date && filters.to_date) {
            update_filters.attendance_date = ['between', [filters.from_date, filters.to_date]];
        } else if (filters.from_date) {
            update_filters.attendance_date = ['>=', filters.from_date];
        } else if (filters.to_date) {
            update_filters.attendance_date = ['<=', filters.to_date];
        }
        
        frappe.call({
            method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.bulk_update_attendance_with_shift_registration',
            args: {
                filters: update_filters
            },
            freeze: true,
            freeze_message: __('Updating attendance records...'),
            callback: function(r) {
                dialog.hide();
                
                if (r.message && r.message.success) {
                    show_bulk_update_results(r.message);
                    // Refresh list view
                    frappe.views.list_view && frappe.views.list_view['Custom Attendance'] && frappe.views.list_view['Custom Attendance'].refresh();
                } else {
                    frappe.msgprint(__('Error: ') + (r.message ? r.message.message : 'Unknown error'));
                }
            }
        });
    });
}

// 6. HIỂN THỊ KẾT QUẢ BULK UPDATE
function show_bulk_update_results(result) {
    let html = `
        <div class="bulk-update-results">
            <h4>Bulk Update Results</h4>
            <div class="row">
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h5 class="text-primary">${result.total_records}</h5>
                            <p>Total Records</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h5 class="text-success">${result.updated_count}</h5>
                            <p>Updated</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h5 class="text-warning">${result.skipped_count}</h5>
                            <p>Skipped</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <h5 class="text-danger">${result.error_count}</h5>
                            <p>Errors</p>
                        </div>
                    </div>
                </div>
            </div>
            
            <h5>Detailed Results:</h5>
            <table class="table table-bordered">
                <thead>
                    <tr>
                        <th>Employee</th>
                        <th>Date</th>
                        <th>Status</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    result.results.forEach(function(record) {
        let statusClass = '';
        let details = '';
        
        switch(record.status) {
            case 'updated':
                statusClass = 'text-success';
                details = `${record.old_shift} → ${record.new_shift}<br>Hours: ${record.old_working_hours} → ${record.new_working_hours}`;
                break;
            case 'skipped':
                statusClass = 'text-warning';
                details = record.reason;
                break;
            case 'error':
                statusClass = 'text-danger';
                details = record.reason;
                break;
        }
        
        html += `
            <tr>
                <td>${record.employee}</td>
                <td>${record.date}</td>
                <td class="${statusClass}">${record.status.toUpperCase()}</td>
                <td>${details}</td>
            </tr>
        `;
    });
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    let results_dialog = new frappe.ui.Dialog({
        title: __('Bulk Update Results'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'results_html',
                options: html
            }
        ],
        primary_action_label: __('Close'),
        primary_action: function() {
            results_dialog.hide();
        }
    });
    
    results_dialog.show();
}

// 7. DIALOG ĐỂ CHECK UPDATEABLE RECORDS
function show_updateable_records_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Check Updateable Records'),
        fields: [
            {
                fieldtype: 'Link',
                fieldname: 'employee',
                label: 'Employee (Optional)',
                options: 'Employee'
            },
            {
                fieldtype: 'Date',
                fieldname: 'from_date',
                label: 'From Date',
                default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)
            },
            {
                fieldtype: 'Date',
                fieldname: 'to_date', 
                label: 'To Date',
                default: frappe.datetime.get_today()
            }
        ],
        primary_action_label: __('Check'),
        primary_action: function(values) {
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.get_attendance_records_for_update',
                args: values,
                freeze: true,
                callback: function(r) {
                    if (r.message && r.message.success) {
                        dialog.hide();
                        show_preview_results(r.message.records, r.message.updateable_count, null);
                    }
                }
            });
        }
    });
    
    dialog.show();
}