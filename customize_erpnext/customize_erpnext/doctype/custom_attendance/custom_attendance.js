


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
        '<span class="badge badge-success">Linked</span>' :
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

