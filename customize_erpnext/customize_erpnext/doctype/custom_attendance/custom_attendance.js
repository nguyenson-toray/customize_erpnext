frappe.ui.form.on('Custom Attendance', {
  refresh: function (frm) {

    // Add custom button in toolbar
    if (!frm.doc.__islocal && frm.doc.docstatus === 0) {
      frm.add_custom_button(__('Sync from Check-in'), function () {
        frm.trigger('sync_button');
      }, __('Actions'));
    }

    // Set filters for linked fields
    frm.set_query('employee', function () {
      return {
        filters: {
          status: 'Active'
        }
      };
    });

    // Load Employee Checkin connections if document exists
    if (!frm.doc.__islocal && frm.doc.employee && frm.doc.attendance_date) {
      setTimeout(function () {
        frm.trigger('load_employee_checkin_connections');
      }, 1000);
    }
  },

  load_employee_checkin_connections: function (frm) {
    if (!frm.doc.employee || !frm.doc.attendance_date) {
      render_connections_html_direct(frm, []);
      return;
    }

    // Direct frappe.call to get checkins
    frappe.call({
      method: 'frappe.client.get_list',
      args: {
        doctype: 'Employee Checkin',
        filters: {
          employee: frm.doc.employee,
          time: ['between', [
            frm.doc.attendance_date + ' 00:00:00',
            frm.doc.attendance_date + ' 23:59:59'
          ]]
        },
        fields: ['name', 'time', 'log_type', 'device_id', 'shift', 'attendance'],
        order_by: 'time asc'
      },
      callback: function (r) {

        if (r.message && r.message.length > 0) {
          render_connections_html_direct(frm, r.message);
        } else {
          render_connections_html_direct(frm, []);
        }
      },
      error: function (r) {
        console.error('Error loading checkins:', r);
        render_connections_html_direct(frm, []);
      }
    });
  },

  render_connections_html: function (frm, checkins) {

    if (!checkins) {
      checkins = [];
    }
    let html = '';

    if (checkins.length === 0) {
      html = `
        <div class="alert alert-info" style="margin: 10px 0;">
          <h6>No Employee Check-ins found</h6>
          <p>No check-in records found for ${frm.doc.employee || 'this employee'} on ${frm.doc.attendance_date || 'this date'}.</p>
          <small>Debug info: Employee=${frm.doc.employee}, Date=${frm.doc.attendance_date}</small>
        </div>
      `;
    } else {
      // Header
      html += `
        <div class="connections-header" style="margin-bottom: 15px;">
          <h5 style="margin: 0; color: #333;">Employee Check-ins (${checkins.length} records)</h5>
          <small class="text-muted">Check-in records for ${frm.doc.employee_name || frm.doc.employee} on ${frappe.datetime.str_to_user(frm.doc.attendance_date)}</small>
        </div>
      `;

      // Table
      html += `
        <div class="table-responsive">
          <table class="table table-bordered table-sm">
            <thead style="background-color: #f8f9fa;">
              <tr>
                <th>Time</th>
                <th>Type</th>
                <th>Device</th>
                <th>Shift</th>
                <th>Linked</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
      `;

      checkins.forEach(function (checkin, index) {
        console.log(checkin.attendance, frm.doc.name);
        let time_formatted = checkin.time ? frappe.datetime.str_to_user(checkin.time) : 'N/A';
        let log_type_badge = checkin.log_type === 'IN' ?
          '<span class="badge badge-success">IN</span>' :
          '<span class="badge badge-warning">OUT</span>';

        let linked_status = checkin.attendance === frm.doc.name ?
          '<span class="badge badge-success">Linked</span>' :
          '<span class="badge badge-light">Not Linked</span>';

        html += `
          <tr>
            <td>${time_formatted}</td>
            <td>${log_type_badge}</td>
            <td>${checkin.device_id || '-'}</td>
            <td>${checkin.shift || '-'}</td>
            <td>${linked_status}</td>
            <td>
              <a href="/app/employee-checkin/${checkin.name}" target="_blank" class="btn btn-xs btn-default">
                View
              </a>
            </td>
          </tr>
        `;
      });

      html += `
            </tbody>
          </table>
        </div>
      `;

      // Summary
      let linked_count = checkins.filter(c => c.attendance === frm.doc.name).length;
      html += `
        <div class="connections-summary" style="margin-top: 10px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">
          <small>
            <strong>Summary:</strong> ${checkins.length} total check-ins, ${linked_count} linked to this attendance record
          </small>
        </div>
      `;
    }

    // Debug: check if field exists
    let field = frm.get_field('connections_html');

    // Set HTML to field - try multiple methods
    try {
      frm.set_df_property('connections_html', 'options', html);
    } catch (e) {
      console.error('Error setting via set_df_property:', e);
    }

    try {
      frm.refresh_field('connections_html');
    } catch (e) {
      console.error('Error refreshing field:', e);
    }

    // Alternative method
    try {
      if (field && field.$wrapper) {
        field.$wrapper.html(html);
      }
    } catch (e) {
      console.error('Error setting via wrapper:', e);
    }

    // Check if HTML was actually set
  },

  sync_button: function (frm) {
    if (!frm.doc.employee || !frm.doc.attendance_date) {
      frappe.msgprint(__('Please select Employee and Attendance Date first'));
      return;
    }

    frappe.call({
      method: 'sync_from_checkin',
      doc: frm.doc,
      freeze: true,
      freeze_message: __('Syncing attendance data...'),
      callback: function (r) {
        if (r.message) {
          frappe.show_alert({
            message: __('Sync Result: ') + r.message,
            indicator: 'green'
          });
          // Reload connections after sync
          setTimeout(() => {
            frm.trigger('load_employee_checkin_connections');
          }, 1000);
          frm.reload_doc();
        }
      },
      error: function (r) {
        console.error('Sync error:', r);
        frappe.msgprint(__('Error occurred while syncing attendance'));
      }
    });
  },

  employee: function (frm) {

    if (frm.doc.employee) {
      // Auto-populate related fields
      frappe.call({
        method: 'frappe.client.get',
        args: {
          doctype: 'Employee',
          name: frm.doc.employee
        },
        callback: function (r) {
          if (r.message) {
            frm.set_value('employee_name', r.message.employee_name);
            frm.set_value('company', r.message.company);
            frm.set_value('department', r.message.department);

            if (r.message.default_shift) {
              frm.set_value('shift', r.message.default_shift);
            }
          }
        }
      });

      // Reload connections if attendance_date is also set
      if (frm.doc.attendance_date && !frm.doc.__islocal) {
        setTimeout(() => {
          frm.trigger('load_employee_checkin_connections');
        }, 1500);
      }
    }
  },

  attendance_date: function (frm) {

    if (frm.doc.attendance_date && frm.doc.employee) {
      // Clear previous attendance data when date changes
      frm.set_value('check_in', '');
      frm.set_value('check_out', '');
      frm.set_value('in_time', '');
      frm.set_value('out_time', '');
      frm.set_value('working_hours', 0);
      frm.set_value('late_entry', 0);
      frm.set_value('early_exit', 0);
      frm.set_value('last_sync_time', '');
      frm.set_value('status', 'Absent');

      // Reload connections if not a new document
      if (!frm.doc.__islocal) {
        setTimeout(() => {
          frm.trigger('load_employee_checkin_connections');
        }, 1500);
      }

      frappe.show_alert({
        message: __('Attendance data cleared for new date. Click "Sync from Check-in" to load data.'),
        indicator: 'blue'
      });
    }
  },

  check_in: function (frm) {
    frm.trigger('calculate_working_hours');
    frm.trigger('update_status');
  },

  check_out: function (frm) {
    frm.trigger('calculate_working_hours');
    frm.trigger('update_status');
  },

  calculate_working_hours: function (frm) {
    if (frm.doc.check_in && frm.doc.check_out) {
      let check_in = moment(frm.doc.check_in);
      let check_out = moment(frm.doc.check_out);

      if (check_out.isAfter(check_in)) {
        let duration = moment.duration(check_out.diff(check_in));
        let hours = duration.asHours();
        frm.set_value('working_hours', Math.round(hours * 100) / 100);

        // Set in_time and out_time
        frm.set_value('in_time', moment(frm.doc.check_in).format('HH:mm:ss'));
        frm.set_value('out_time', moment(frm.doc.check_out).format('HH:mm:ss'));
      } else {
        frappe.msgprint(__('Check-out time cannot be earlier than check-in time'));
        frm.set_value('check_out', '');
      }
    }
  },

  update_status: function (frm) {
    if (frm.doc.check_in) {
      if (!frm.doc.status || frm.doc.status === 'Absent') {
        frm.set_value('status', 'Present');
      }
    }
  },

  auto_sync_enabled: function (frm) {
    if (frm.doc.auto_sync_enabled && frm.doc.employee && frm.doc.attendance_date) {
      frappe.show_alert({
        message: __('Auto sync enabled. Attendance will be automatically updated from check-ins.'),
        indicator: 'blue'
      });
    }
  }
});

// Manual trigger for debugging
// frappe.ui.form.on('Custom Attendance', {
//   after_load: function (frm) {
//     console.log('Form loaded, document:', frm.doc);
//     console.log('connections_html field:', frm.get_field('connections_html'));
//   }
// });

// List View customizations
frappe.listview_settings['Custom Attendance'] = {
  add_fields: ['status', 'working_hours', 'auto_sync_enabled', 'docstatus'],
  // Add bulk action button trong list view
  onload: function (listview) {
    // Add Bulk Create button cho HR Manager và System Manager
    if (frappe.user.has_role('HR Manager') || frappe.user.has_role('System Manager')) {
      listview.page.add_menu_item(__('Bulk Create from Shift Date'), function () {
        show_bulk_process_dialog();
      });
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

// Debug function to manually trigger connection loading
// window.debug_load_connections = function () {
//   let frm = cur_frm;
//   if (frm && frm.doc.name) {
//     console.log('Manual debug trigger for:', frm.doc.name);
//     frm.trigger('load_employee_checkin_connections');
//   } else {
//     console.log('No current form found');
//   }
// };

// Direct render function
function render_connections_html_direct(frm, checkins) {
  if (!checkins) {
    checkins = [];
  }

  let html = '';

  if (checkins.length === 0) {
    html = `
      <div class="alert alert-info" style="margin: 10px 0;">
        <h6>No Employee Check-ins found</h6>
        <p>No check-in records found for ${frm.doc.employee || 'this employee'} on ${frm.doc.attendance_date || 'this date'}.</p>
        <small>Debug info: Employee=${frm.doc.employee}, Date=${frm.doc.attendance_date}</small>
      </div>
    `;
  } else {
    // Header
    html += `
      <div class="connections-header" style="margin-bottom: 15px;">
        <h5 style="margin: 0; color: #333;">Employee Check-ins (${checkins.length} records)</h5>
        <small class="text-muted">Check-in records for ${frm.doc.employee_name || frm.doc.employee} on ${frappe.datetime.str_to_user(frm.doc.attendance_date)}</small>
      </div>
    `;

    // Table
    html += `
      <div class="table-responsive">
        <table class="table table-bordered table-sm">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th>Time</th>
              <th>Check-in Record</th>
              <th>Type</th>
              <th>Device</th>
              <th>Shift</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
    `;

    checkins.forEach(function (checkin, index) {

      let time_formatted = checkin.time ? frappe.datetime.str_to_user(checkin.time) : 'N/A';
      let checkin_link = `<a href="/app/employee-checkin/${checkin.name}" target="_blank" class="text-primary">${checkin.name}</a>`;
      let log_type_badge = checkin.log_type === 'IN' ?
        '<span class="badge badge-success">IN</span>' :
        (checkin.log_type === 'OUT' ? '<span class="badge badge-warning">OUT</span>' : '<span class="badge badge-secondary">-</span>');

      let linked_status = checkin.attendance === frm.doc.name ?
        '<span class="badge badge-success">✓ Linked</span>' :
        '<span class="badge badge-light">Not Linked</span>';

      html += `
        <tr>
          <td>${time_formatted}</td>
          <td>${checkin_link}</td>
          <td>${log_type_badge}</td>
          <td>${checkin.device_id || '-'}</td>
          <td>${checkin.shift || '-'}</td>
          <td>${linked_status}</td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;

    // Summary
    let linked_count = checkins.filter(c => c.attendance === frm.doc.name).length;
    html += `
      <div class="connections-summary" style="margin-top: 10px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">
        <small>
          <strong>Summary:</strong> ${checkins.length} total check-ins, ${linked_count} linked to this attendance record
        </small>
      </div>
    `;
  }

  // Debug: check if field exists
  let field = frm.get_field('connections_html');

  // Set HTML to field - try multiple methods
  try {
    frm.set_df_property('connections_html', 'options', html);
  } catch (e) {
    console.error('Error setting via set_df_property:', e);
  }

  try {
    frm.refresh_field('connections_html');
  } catch (e) {
    console.error('Error refreshing field:', e);
  }

  // Alternative method
  try {
    if (field && field.$wrapper) {
      field.$wrapper.html(html);
    }
  } catch (e) {
    console.error('Error setting via wrapper:', e);
  }

}

// syn manual:
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
      if (r.message && r.message.success) {
        render_preview_html(dialog, r.message);
      } else {
        frappe.msgprint(__('Error getting preview: ') + (r.message.message || 'Unknown error'));
      }
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

  // Confirm before processing
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

      // Show progress dialog
      let progress_dialog = show_progress_dialog();
      dialog.hide();

      frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.bulk_process_from_shift_date',
        args: args,
        freeze: false, // Don't freeze để có thể show progress
        callback: function (r) {
          progress_dialog.hide();

          if (r.message && r.message.success) {
            show_results_dialog(r.message);
          } else {
            frappe.msgprint(__('Bulk Process Error: ') + (r.message.message || 'Unknown error'));
          }
        },
        error: function (r) {
          progress_dialog.hide();
          frappe.msgprint(__('System Error: Please check error logs'));
        }
      });
    }
  );
}

function show_progress_dialog() {
  let progress_dialog = new frappe.ui.Dialog({
    title: __('Bulk Processing in Progress'),
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
  let status_icon = results.error_count === 0 ? 'ok' : 'warning';

  let html = `
    <div class="${status_class} alert">
      <h5>${status_icon} Bulk Processing Completed</h5>
      <div class="row">
        <div class="col-md-6">
          <p><strong> Days Processed:</strong> ${results.total_days}</p>
          <p><strong> Employee-Days Found:</strong> ${results.total_employees}</p>
        </div>
        <div class="col-md-6">
          <p><strong> Records Created:</strong> ${results.created_count}</p>
          <p><strong> Successfully Synced:</strong> ${results.synced_count}</p>
          <p><strong> Errors:</strong> ${results.error_count}</p>
        </div>
      </div>
    </div>
  `;

  // Add daily details if available
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

  // Add errors if any
  if (results.errors && results.errors.length > 0) {
    html += `
      <h6 style="margin-top: 15px;">Error Details:</h6>
      <div style="max-height: 150px; overflow-y: auto; background-color: #f8f9fa; padding: 10px; border-radius: 4px;">
    `;

    results.errors.slice(0, 20).forEach(function (error) {  // Show max 20 errors
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

      // Refresh current form if it's Custom Attendance
      if (cur_frm && cur_frm.doc.doctype === 'Custom Attendance') {
        cur_frm.reload_doc();
      }
    }
  });

  results_dialog.show();
}