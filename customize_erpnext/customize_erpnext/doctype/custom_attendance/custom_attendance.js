// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

frappe.ui.form.on('Custom Attendance', {
  refresh: function (frm) {
    // Add custom button in toolbar
    if (!frm.doc.__islocal && frm.doc.docstatus === 0) {
      frm.add_custom_button(__('Sync from Check-in'), function () {
        frm.trigger('sync_button');
      }, __('Actions'));
      
      // Add overtime recalculation button if check-in/out exists
      if (frm.doc.check_in && frm.doc.check_out) {
        frm.add_custom_button(__('Recalculate with Overtime'), function () {
          frm.trigger('recalculate_overtime_btn');
        }, __('Actions'));
      }
    }

    // Set filters for linked fields
    frm.set_query('employee', function () {
      return {
        filters: {
          status: 'Active'
        }
      };
    });

    // Load connections and overtime details if document exists
    if (!frm.doc.__islocal && frm.doc.employee && frm.doc.attendance_date) {
      setTimeout(function () {
        frm.trigger('load_employee_checkin_connections');
        frm.trigger('load_overtime_details');
      }, 1000);
    }
  },

  load_overtime_details: function (frm) {
    if (!frm.doc.employee || !frm.doc.attendance_date) {
     
      render_overtime_html(frm, { has_overtime: false });
      return;
    }

    frappe.call({
      method: 'get_overtime_details',
      doc: frm.doc,
      callback: function (r) {
        if (r.message) {
          
          render_overtime_html(frm, r.message);
        } else {
          render_overtime_html(frm, { has_overtime: false });
        }
      },
      error: function (r) {
        console.error('Error loading overtime details:', r);
        render_overtime_html(frm, { has_overtime: false, error: 'Failed to load' });
      }
    });
  },

  recalculate_overtime_btn: function (frm) {
  if (!frm.doc.check_in || !frm.doc.check_out) {
    frappe.msgprint(__('Please ensure both check-in and check-out times are set'));
    return;
  }

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.custom_attendance.recalculate_attendance_with_overtime',
    args: {
      attendance_name: frm.doc.name
    },
    freeze: true,
    freeze_message: __('Recalculating overtime...'),
    callback: function (r) {
      if (r.message && r.message.success) {
        // GET CURRENT VALUES
        let current_working_hours = frm.doc.working_hours || 8.0;
        let overtime_hours = r.message.overtime_hours || 0.0;
        
        // CALCULATE TOTAL = REGULAR + OVERTIME
        let total_working_hours = current_working_hours + overtime_hours;

        // UPDATE BOTH FIELDS
        frappe.call({
          method: 'frappe.client.set_value',
          args: {
            doctype: 'Custom Attendance',
            name: frm.doc.name,
            fieldname: {
              'overtime_hours': overtime_hours,
              'working_hours': total_working_hours  // ← KEY FIX
            }
          },
          callback: function(update_r) {
            if (!update_r.exc) {
              frappe.show_alert({
                message: `Updated: ${current_working_hours}h + ${overtime_hours}h = ${total_working_hours}h total`,
                indicator: 'green'
              });

              // Show detailed results  
              frappe.msgprint({
                title: __('Overtime Calculation Results'),
                message: `
                  <div class="alert alert-success">
                    <h6>✅ Overtime Updated Successfully</h6>
                    <p><strong>Regular Hours:</strong> ${current_working_hours} hours</p>
                    <p><strong>Overtime Hours:</strong> ${overtime_hours} hours</p>
                    <p><strong>Total Working Hours:</strong> ${total_working_hours} hours</p>
                  </div>
                `,
                indicator: 'green'
              });

              // Reload document
              frm.reload_doc();
              // setTimeout(() => {
              //   frm.trigger('load_overtime_details');
              // }, 1000);
            }
          }
        });

      } else {
        frappe.msgprint(__('Error: ') + (r.message ? r.message.message : 'Unknown error'));
      }
    },
    error: function (r) {
      console.error('Recalculate overtime error:', r);
      frappe.msgprint(__('Error occurred while recalculating overtime'));
    }
  });
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

  sync_button: function (frm) {
    if (!frm.doc.employee || !frm.doc.attendance_date) {
      frappe.msgprint(__('Please select Employee and Attendance Date first'));
      return;
    }

    frappe.call({
      method: 'sync_from_checkin',
      doc: frm.doc,
      freeze: true,
      freeze_message: __('Syncing attendance data with overtime...'),
      callback: function (r) {
        if (r.message) {
          frappe.show_alert({
            message: __('Sync Result: ') + r.message,
            indicator: 'green'
          });
          
          // Reload connections and overtime details after sync
          // setTimeout(() => {
            // frm.trigger('load_employee_checkin_connections');
            // frm.trigger('load_overtime_details');
          // }, 1000);
          
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

      // Clear overtime details and reload if attendance_date is also set
      if (frm.doc.attendance_date && !frm.doc.__islocal) {
        frm.set_value('overtime_hours', 0);
        render_overtime_html(frm, { has_overtime: false });
        
        setTimeout(() => {
          frm.trigger('load_employee_checkin_connections');
          frm.trigger('load_overtime_details');
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
      frm.set_value('overtime_hours', 0);
      frm.set_value('late_entry', 0);
      frm.set_value('early_exit', 0);
      frm.set_value('last_sync_time', '');
      frm.set_value('status', 'Absent');

      // Clear overtime details
      render_overtime_html(frm, { has_overtime: false });

      // Reload connections and overtime if not a new document
      if (!frm.doc.__islocal) {
        setTimeout(() => {
          frm.trigger('load_employee_checkin_connections');
          // frm.trigger('load_overtime_details');
        }, 1500);
      }

      frappe.show_alert({
        message: __('Attendance data cleared for new date. Click "Sync from Check-in" to load data with overtime.'),
        indicator: 'blue'
      });
    }
  },

  check_in: function (frm) {
    frm.trigger('calculate_working_hours');
    frm.trigger('update_status');
    
    // Reload overtime details if both check-in and check-out exist
    if (frm.doc.check_in && frm.doc.check_out && !frm.doc.__islocal) {
      setTimeout(() => {
        // frm.trigger('load_overtime_details');
      }, 500);
    }
  },

  check_out: function (frm) {
    frm.trigger('calculate_working_hours');
    frm.trigger('update_status');
    if (frm.doc.check_in && frm.doc.check_out) {
        setTimeout(() => {
            frm.trigger('auto_calculate_overtime');
        }, 1000);
    }
    // Reload overtime details if both check-in and check-out exist
    if (frm.doc.check_in && frm.doc.check_out && !frm.doc.__islocal) {
      setTimeout(() => {
        // frm.trigger('load_overtime_details');
      }, 500);
    }
  },

  calculate_working_hours: function (frm) {
    if (frm.doc.check_in && frm.doc.check_out) {
      let check_in = moment(frm.doc.check_in);
      let check_out = moment(frm.doc.check_out);

      if (check_out.isAfter(check_in)) {
        let duration = moment.duration(check_out.diff(check_in));
        let hours = duration.asHours();
        
        // This is basic calculation - server-side will handle overtime properly
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
        message: __('Auto sync enabled. Attendance will be automatically updated from check-ins including overtime.'),
        indicator: 'blue'
      });
    }
  }
});

// Function to render overtime details HTML
function render_overtime_html(frm, overtime_data) {
  let html = '';

  if (!overtime_data.has_overtime) {
    html = `
      <div class="alert alert-info" style="margin: 10px 0;">
        <h6>No Overtime Requests</h6>
        <p>No approved overtime requests found for ${frm.doc.employee || 'this employee'} on ${frm.doc.attendance_date || 'this date'}.</p>
        ${overtime_data.error ? `<small class="text-danger">Error: ${overtime_data.error}</small>` : ''}
      </div>
    `;
  } else {
    // Header
    html += `
      <div class="overtime-header" style="margin-bottom: 15px;">
        <h5 style="margin: 0; color: #333;">Overtime Requests (${overtime_data.total_requests} found)</h5>
        <small class="text-muted">Total Actual OT Hours: <strong>${overtime_data.total_actual_ot_hours} hours</strong></small>
      </div>
    `;

    // Table
    html += `
      <div class="table-responsive">
        <table class="table table-bordered table-sm">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th>OT Request</th>
              <th>Planned Time</th>
              <th>Planned Hours</th>
              <th>Actual Hours</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
    `;

    overtime_data.requests.forEach(function (ot_req) {
      let status_badge = ot_req.actual_hours > 0 ?
        '<span class="badge badge-success">Applied</span>' :
        '<span class="badge badge-secondary">No Overlap</span>';

      let actual_hours_display = ot_req.actual_hours > 0 ?
        `<strong>${ot_req.actual_hours} hrs</strong>` :
        '<span class="text-muted">0 hrs</span>';

      html += `
        <tr>
          <td><a href="/app/overtime-request/${ot_req.request_name}" target="_blank" class="text-primary">${ot_req.request_name}</a></td>
          <td>${ot_req.planned_from} - ${ot_req.planned_to}</td>
          <td>${ot_req.planned_hours} hrs</td>
          <td>${actual_hours_display}</td>
          <td>${status_badge}</td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;

    // Summary
    html += `
      <div class="overtime-summary" style="margin-top: 10px; padding: 10px; background-color: #f8f9fa; border-radius: 4px;">
        <small>
          <strong>Calculation Logic:</strong> Overtime hours are calculated based on actual check-in/out times vs planned OT times.
          If you check out before OT end time, only actual worked OT hours are counted.
        </small>
      </div>
    `;
  }

  // Set HTML to field
  try {
    frm.set_df_property('overtime_details_html', 'options', html);
    frm.refresh_field('overtime_details_html');
  } catch (e) {
    console.error('Error setting overtime HTML:', e);
  }
}

// Direct render function for connections (keeping existing function)
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

  // Set HTML to field
  try {
    frm.set_df_property('connections_html', 'options', html);
    frm.refresh_field('connections_html');
  } catch (e) {
    console.error('Error setting connections HTML:', e);
  }
}

