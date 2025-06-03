// Enhanced List View customizations với Daily Completion features
frappe.listview_settings['Custom Attendance'] = {
  add_fields: ['status', 'working_hours', 'auto_sync_enabled', 'docstatus'],
  onload: function (listview) {

    // Add Bulk Create button cho HR Manager và System Manager
    if (frappe.user.has_role('HR Manager') || frappe.user.has_role('System Manager')) {
      setTimeout(function () {
        try {
          // Bulk Create from Shift Date button
          listview.page.add_menu_item(__('Bulk Create from Shift Date'), function () {
            show_bulk_process_dialog();
          });

          // NEW: Daily Completion button
          listview.page.add_menu_item(__('Daily Attendance Completion'), function () {
            show_daily_completion_dialog();
          });

          // NEW: Check Missing Attendance button  
          listview.page.add_menu_item(__('Check Missing Attendance'), function () {
            show_missing_attendance_dialog();
          });

          console.log('Enhanced Custom Attendance buttons added successfully');
        } catch (e) {
          console.error('Failed to add enhanced buttons:', e);
        }
      }, 300);
    }
  },
  get_indicator: function (doc) {
    if (doc.docstatus === 1) {
      if (doc.status === 'Present') {
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

// EXISTING: Bulk process dialog functions
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
              <li><strong>Process:</strong> Create attendance → Auto sync from check-ins → Report results</li>
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

// NEW: Daily Completion Dialog
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
          // depends_on sẽ tự động handle việc show/hide
          // Chỉ cần refresh layout
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

// NEW: Missing Attendance Dialog
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

// NEW: Check attendance summary
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
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.get_attendance_summary_for_date',
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
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.get_attendance_summary_for_range',
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

// NEW: Check missing attendance

function render_range_summary_html(dialog, data) {
  let html = `
    <div class="summary-results" style="margin-top: 15px;">
      <div class="alert alert-info">
        <h6><strong>Date Range Summary: ${frappe.datetime.str_to_user(data.start_date)} to ${frappe.datetime.str_to_user(data.end_date)}</strong></h6>
        <div class="row">
          <div class="col-md-6">
            <p><strong>Total Days:</strong> ${data.total_days}</p>
            <p><strong>Total Employee-Days:</strong> ${data.total_employee_days}</p>
            <p><strong>Missing Records:</strong> <span class="badge badge-warning">${data.total_missing}</span></p>
          </div>
          <div class="col-md-6">
            <p><strong>Avg Daily Employees:</strong> ${Math.round(data.total_employee_days / data.total_days)}</p>
            <p><strong>Completion Rate:</strong> ${data.completion_percentage}%</p>
          </div>
        </div>
      </div>
  `;

  if (data.daily_breakdown && data.daily_breakdown.length > 0) {
    html += `
      <div class="table-responsive" style="max-height: 200px; overflow-y: auto;">
        <table class="table table-bordered table-sm">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th>Date</th>
              <th>Active Employees</th>
              <th>Attendance Records</th>
              <th>Missing</th>
              <th>Completion %</th>
            </tr>
          </thead>
          <tbody>
    `;

    data.daily_breakdown.forEach(function (row) {
      let completion_rate = row.total_employees > 0 ? ((row.attendance_records / row.total_employees) * 100).toFixed(1) : '0.0';
      let missing_count = row.total_employees - row.attendance_records;

      html += `
        <tr>
          <td>${frappe.datetime.str_to_user(row.date)}</td>
          <td>${row.total_employees}</td>
          <td>${row.attendance_records}</td>
          <td><span class="badge ${missing_count > 0 ? 'badge-warning' : 'badge-success'}">${missing_count}</span></td>
          <td>${completion_rate}%</td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;
  }

  if (data.total_missing > 0) {
    html += `
      <div class="alert alert-warning">
        <strong>Action Needed:</strong> ${data.total_missing} attendance records are missing across the date range.
        Click "Start Completion" to create these missing records.
      </div>
    `;
  } else {
    html += `
      <div class="alert alert-success">
        <strong>Complete:</strong> All employees have attendance records for the selected date range.
      </div>
    `;
  }

  html += '</div>';

  dialog.set_df_property('summary_html', 'options', html);
}
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


// NEW: Check missing attendance
function check_missing_attendance(dialog) {
  let values = dialog.get_values();

  if (!values.check_date) {
    frappe.msgprint(__('Please select a date'));
    return;
  }

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.identify_missing_attendance',
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

// NEW: Create missing attendance
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
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.manual_daily_completion',
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

function execute_single_date_completion(date, dialog) {
  let progress_dialog = show_progress_dialog();
  dialog.hide();

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.manual_daily_completion',
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

function execute_date_range_completion(start_date, end_date, dialog) {
  let progress_dialog = show_progress_dialog();
  dialog.hide();

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.bulk_daily_completion',
    args: {
      start_date: start_date,
      end_date: end_date
    },
    freeze: false,
    callback: function (r) {
      progress_dialog.hide();

      if (r && r.message && r.message.success) {
        show_bulk_completion_results_dialog(r.message);
      } else {
        frappe.msgprint(__('Bulk Daily Completion Error: ') + (r.message && r.message.message ? r.message.message : 'Unknown error'));
      }
    },
    error: function (r) {
      progress_dialog.hide();
      console.error('Date range completion call error:', r);
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

// NEW: Show bulk completion results
function show_bulk_completion_results_dialog(results) {
  let status_class = results.total_errors === 0 ? 'alert-success' : 'alert-warning';

  let html = `
    <div class="${status_class} alert">
      <h5>Bulk Daily Completion Results</h5>
      <p><strong>Date Range:</strong> ${frappe.datetime.str_to_user(results.start_date)} to ${frappe.datetime.str_to_user(results.end_date)}</p>
      <div class="row">
        <div class="col-md-4">
          <p><strong>Total Created:</strong> ${results.total_created}</p>
        </div>
        <div class="col-md-4">
          <p><strong>Total Updated:</strong> ${results.total_updated}</p>
        </div>
        <div class="col-md-4">
          <p><strong>Total Errors:</strong> ${results.total_errors}</p>
        </div>
      </div>
    </div>
  `;

  // Add daily breakdown if available
  if (results.daily_results && results.daily_results.length > 0) {
    html += `
      <h6>Daily Breakdown:</h6>
      <div class="table-responsive" style="max-height: 300px; overflow-y: auto;">
        <table class="table table-sm">
          <thead><tr><th>Date</th><th>Created</th><th>Updated</th><th>Errors</th></tr></thead>
          <tbody>
    `;

    results.daily_results.forEach(function (day) {
      html += `
        <tr>
          <td>${frappe.datetime.str_to_user(day.date)}</td>
          <td><span class="badge badge-success">${day.created}</span></td>
          <td><span class="badge badge-info">${day.updated}</span></td>
          <td>${day.errors > 0 ? `<span class="badge badge-danger">${day.errors}</span>` : '-'}</td>
        </tr>
      `;
    });

    html += '</tbody></table></div>';
  }

  // Add errors if any
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
    title: __('Bulk Completion Results'),
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

// EXISTING functions (show_preview, start_bulk_process, etc.)
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
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.get_bulk_process_preview',
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

function render_preview_html(dialog, data) {
  let html = `
    <div class="preview-results" style="margin-top: 15px;">
      <div class="alert alert-success">
        <h6><strong>Preview Results</strong></h6>
        <div class="row">
          <div class="col-md-6">
            <p><strong>Date Range:</strong> ${data.start_date} to ${data.end_date}</p>
            <p><strong>Total Days:</strong> ${data.total_days} days</p>
          </div>
          <div class="col-md-6">
            <p><strong>Total Employees:</strong> ${data.total_employees} employee-days</p>
            <p><strong>Shift:</strong> ${data.shift_name || 'All Shifts'}</p>
          </div>
        </div>
      </div>
  `;

  if (data.daily_breakdown && data.daily_breakdown.length > 0) {
    html += `
      <div class="table-responsive" style="max-height: 300px; overflow-y: auto;">
        <table class="table table-bordered table-sm">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th>Date</th>
              <th>Employees</th>
              <th>Check-ins</th>
              <th>Shifts</th>
            </tr>
          </thead>
          <tbody>
    `;

    data.daily_breakdown.forEach(function (row) {
      html += `
        <tr>
          <td>${frappe.datetime.str_to_user(row.attendance_date)}</td>
          <td><span class="badge badge-primary">${row.employee_count}</span></td>
          <td>${row.checkin_count}</td>
          <td>${row.shift_count}</td>
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
      <div class="alert alert-warning">
        <strong>No Data Found</strong><br>
        No employees with check-ins found in the selected date range, or all records already exist.
      </div>
    `;
  }

  html += '</div>';

  dialog.set_df_property('preview_html', 'options', html);
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
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.bulk_process_from_shift_date',
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

function show_progress_dialog() {
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
            <h5 style="margin-top: 20px;">Processing Custom Attendance Records...</h5>
            <p class="text-muted">This may take several minutes. Please wait...</p>
          </div>
        `
      }
    ]
  });

  progress_dialog.show();
  return progress_dialog;
}

function show_results_dialog(results) {
  let status_class = results.error_count === 0 ? 'alert-success' : 'alert-warning';

  let html = `
    <div class="${status_class} alert">
      <h5>Bulk Processing Completed</h5>
      <div class="row">
        <div class="col-md-6">
          <p><strong>Days Processed:</strong> ${results.total_days}</p>
          <p><strong>Employee-Days Found:</strong> ${results.total_employees}</p>
        </div>
        <div class="col-md-6">
          <p><strong>Records Created:</strong> ${results.created_count}</p>
          <p><strong>Successfully Synced:</strong> ${results.synced_count}</p>
          <p><strong>Errors:</strong> ${results.error_count}</p>
        </div>
      </div>
    </div>
  `;

  if (results.details && results.details.length > 0) {
    html += `
      <h6>Daily Breakdown:</h6>
      <div class="table-responsive" style="max-height: 200px; overflow-y: auto;">
        <table class="table table-sm">
          <thead><tr><th>Date</th><th>Created</th><th>Synced</th><th>Errors</th></tr></thead>
          <tbody>
    `;

    results.details.forEach(function (day) {
      html += `
        <tr>
          <td>${frappe.datetime.str_to_user(day.date)}</td>
          <td><span class="badge badge-success">${day.created}</span></td>
          <td><span class="badge badge-info">${day.synced}</span></td>
          <td>${day.errors > 0 ? `<span class="badge badge-danger">${day.errors}</span>` : '-'}</td>
        </tr>
      `;
    });

    html += '</tbody></table></div>';
  }

  if (results.errors && results.errors.length > 0) {
    html += `
      <h6 style="margin-top: 15px;">Error Details:</h6>
      <div style="max-height: 150px; overflow-y: auto; background-color: #f8f9fa; padding: 10px; border-radius: 4px;">
    `;

    results.errors.slice(0, 20).forEach(function (error) {
      html += `<small class="text-danger">• ${error}</small><br>`;
    });

    if (results.errors.length > 20) {
      html += `<small class="text-muted">... and ${results.errors.length - 20} more errors</small>`;
    }

    html += '</div>';
  }

  let results_dialog = new frappe.ui.Dialog({
    title: __('Bulk Process Results'),
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

      if (cur_list && cur_list.doctype === 'Custom Attendance') {
        cur_list.refresh();
      }
    }
  });

  results_dialog.show();
}