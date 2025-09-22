// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt
// UPDATED for new Overtime Registration structure

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

      // Add test button for debugging
      // frm.add_custom_button(__('Test Overtime Structure'), function () {
      //   frm.trigger('test_overtime_structure');
      // }, __('Debug'));
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

  // UPDATED: Load overtime details with new structure
  load_overtime_details: function (frm) {
  if (!frm.doc.employee || !frm.doc.attendance_date) {
    render_overtime_html(frm, { has_overtime: false });
    return;
  }

  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.get_overtime_details_standalone',
    args: {
      employee: frm.doc.employee,
      attendance_date: frm.doc.attendance_date,
      check_in: frm.doc.check_in || null,
      check_out: frm.doc.check_out || null
    },
    callback: function (r) {
      if (r.message) {
        render_overtime_html(frm, r.message);
      } else {
        render_overtime_html(frm, { has_overtime: false });
      }
    },
    error: function (r) {
      console.error('Standalone API error:', r);
      render_overtime_html(frm, { 
        has_overtime: false, 
        error: 'Unable to load overtime details'
      });
    }
  });
},

  // UPDATED: Recalculate overtime with new method
  recalculate_overtime_btn: function (frm) {
    if (!frm.doc.check_in || !frm.doc.check_out) {
      frappe.msgprint(__('Please ensure both check-in and check-out times are set'));
      return;
    }

    frappe.call({
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.recalculate_attendance_with_overtime',
      args: {
        attendance_name: frm.doc.name
      },
      freeze: true,
      freeze_message: __('Recalculating overtime with new structure...'),
      callback: function (r) {
        if (r.message && r.message.success) {
          // Display detailed results
          let result = r.message;
          
          frappe.msgprint({
            title: __(' Overtime Recalculation Completed'),
            message: `
              <div class="alert alert-success">
                <h6>Overtime Updated Successfully</h6>
                <table class="table table-sm">
                  <tr><td><strong>Before:</strong></td><td>${result.old_working_hours || 0}h working, ${result.old_overtime_hours || 0}h overtime</td></tr>
                  <tr><td><strong>After:</strong></td><td>${result.new_working_hours || 0}h working, ${result.new_overtime_hours || 0}h overtime</td></tr>
                  <tr><td><strong>OT Requests Found:</strong></td><td>${result.ot_requests_found || 0}</td></tr>
                </table>
                <p><strong>Result:</strong> ${result.message}</p>
              </div>
            `,
            indicator: 'green'
          });

          // Reload document and refresh overtime details
          frm.reload_doc();
          setTimeout(() => {
            frm.trigger('load_overtime_details');
          }, 1000);

        } else {
          frappe.msgprint({
            title: __(' Recalculation Failed'),
            message: `<div class="alert alert-danger">
              <p><strong>Error:</strong> ${r.message ? r.message.message : 'Unknown error occurred'}</p>
              <small>Please check if Overtime Registration data exists for this employee and date.</small>
            </div>`,
            indicator: 'red'
          });
        }
      },
      error: function (r) {
        console.error('Recalculate overtime error:', r);
        frappe.msgprint({
          title: __(' System Error'),
          message: `<div class="alert alert-danger">
            <p>Error occurred while recalculating overtime.</p>
            <small>Please check browser console and ensure server functions are properly installed.</small>
          </div>`,
          indicator: 'red'
        });
      }
    });
  },

  // NEW: Test overtime structure
  test_overtime_structure: function (frm) {
    frappe.call({
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.test_with_your_data',
      callback: function (r) {
        if (r.message && r.message.success) {
          let result = r.message.result;
          
          frappe.msgprint({
            title: __('🧪 Overtime Structure Test Results'),
            message: `
              <div class="alert alert-info">
                <h6>Overtime Registration Check</h6>
                <p><strong>Registration:</strong> ${result.overtime_registration_check.name}</p>
                <p><strong>Status:</strong> ${result.overtime_registration_check.status} (docstatus: ${result.overtime_registration_check.docstatus})</p>
                <p><strong>Total Employees:</strong> ${result.overtime_registration_check.total_employees}</p>
                <p><strong>Total Hours:</strong> ${result.overtime_registration_check.total_hours}</p>
                
                <h6 style="margin-top: 15px;">Test Employees Found: ${result.test_employees.length}</h6>
                ${result.test_employees.map(emp => `
                  <small>• ${emp.employee} (${emp.employee_name}) - ${emp.date} - ${emp.begin_time} to ${emp.end_time}</small><br>
                `).join('')}
              </div>
            `,
            indicator: 'blue'
          });
        } else {
          frappe.msgprint(__('Test failed: ') + (r.message ? r.message.error : 'Unknown error'));
        }
      },
      error: function (r) {
        frappe.msgprint(__('Test error - please ensure test functions are installed'));
      }
    });
  },

  // NEW: Auto calculate overtime when check-out changes
  auto_calculate_overtime: function (frm) {
    if (!frm.doc.check_in || !frm.doc.check_out || frm.doc.__islocal) {
      return;
    }

    // Auto-calculate overtime in background
    frappe.call({
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.recalculate_attendance_with_overtime',
      args: {
        attendance_name: frm.doc.name
      },
      callback: function (r) {
        if (r.message && r.message.success) {
          // Show subtle notification
          frappe.show_alert({
            message: `Auto-calculated: ${r.message.new_overtime_hours || 0}h overtime added`,
            indicator: 'green'
          }, 3);
          
          // Update fields without full reload
          frm.set_value('working_hours', r.message.new_working_hours);
          frm.set_value('overtime_hours', r.message.new_overtime_hours);
          
          // Refresh overtime details
          setTimeout(() => {
            frm.trigger('load_overtime_details');
          }, 500);
        }
      },
      error: function (r) {
        console.log('Auto-calculate overtime failed (silent):', r);
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
      method: 'customize_erpnext.customize_erpnext.doctype.custom_attendance.modules.api_methods.sync_from_checkin',
        args: {
          attendance_name: frm.doc.name  // Pass document name như argument
      },
      freeze: true,
      freeze_message: __('Syncing from check-in records...'),
      callback: function (r) {
        if (r.message) {
          console.log(r.message.message);
          frappe.show_alert({
            message: __('') + r.message.message,
            indicator: 'green'
          });
          
          frm.reload_doc();
          
          // Auto-recalculate overtime after sync if check times exist
          setTimeout(() => {
            if (frm.doc.check_in && frm.doc.check_out) {
              frm.trigger('auto_calculate_overtime');
            }
          }, 2000);
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
          frm.trigger('load_overtime_details');
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
        frm.trigger('load_overtime_details');
      }, 500);
    }
  },

  check_out: function (frm) {
    frm.trigger('calculate_working_hours');
    frm.trigger('update_status');
    
    // Auto-calculate overtime when check-out is set
    if (frm.doc.check_in && frm.doc.check_out && !frm.doc.__islocal) {
      setTimeout(() => {
        frm.trigger('auto_calculate_overtime');
      }, 1000);
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

// UPDATED: Function to render overtime details HTML for new structure
function render_overtime_html(frm, overtime_data) {
  let html = '';

  if (!overtime_data.has_overtime) {
    html = `
      <div class="alert alert-info" style="margin: 10px 0;">
        <h6> No Overtime Registrations</h6>
        <p>No approved <strong>Overtime Registration</strong> records found for ${frm.doc.employee || 'this employee'} on ${frm.doc.attendance_date || 'this date'}.</p>
        ${overtime_data.error ? `<small class="text-danger"><strong>Error:</strong> ${overtime_data.error}</small>` : ''}
        <hr>
        <small class="text-muted">
          <strong>Note:</strong> This system now uses <em>Overtime Registration</em> instead of <em>Overtime Request</em>.<br>
          Create an Overtime Registration with status "Approved" and docstatus = 1 (Submitted) to see overtime calculations.
        </small>
      </div>
    `;
  } else {
    // Header with enhanced info
    html += `
      <div class="overtime-header" style="margin-bottom: 15px; padding: 10px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 6px;">
        <h5 style="margin: 0; color: white;"> Overtime Registrations (${overtime_data.total_requests} found)</h5>
        <div style="margin-top: 5px;">
          <span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 12px; font-size: 12px;">
            Total Planned: <strong>${overtime_data.total_planned_hours || 0}h</strong>
          </span>
          <span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px;">
            Total Actual: <strong>${overtime_data.total_actual_ot_hours}h</strong>
          </span>
        </div>
      </div>
    `;

    // Enhanced table
    html += `
      <div class="table-responsive">
        <table class="table table-bordered table-sm" style="margin-bottom: 0;">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th style="width: 20%;"> OT Registration</th>
              <th style="width: 20%;"> Planned Time</th>
              <th style="width: 12%;"> Planned</th>
              <th style="width: 12%;"> Actual</th>
              <th style="width: 15%;"> Status</th>
              <th style="width: 21%;"> Details</th>
            </tr>
          </thead>
          <tbody>
    `;

    overtime_data.requests.forEach(function (ot_req) {
      let status_badge = '';
      let actual_hours_display = '';
      
      if (ot_req.actual_hours > 0) {
        status_badge = '<span class="badge badge-success"> Applied</span>';
        actual_hours_display = `<strong style="color: #28a745;">${ot_req.actual_hours}h</strong>`;
      } else {
        status_badge = '<span class="badge badge-secondary">⏸️ No Overlap</span>';
        actual_hours_display = '<span class="text-muted">0h</span>';
      }

      // Construct details column
      let details = [];
      if (ot_req.reason) details.push(`<strong>Reason:</strong> ${ot_req.reason}`);
      if (ot_req.group) details.push(`<strong>Group:</strong> ${ot_req.group}`);
      if (ot_req.general_reason) details.push(`<strong>General:</strong> ${ot_req.general_reason}`);
      
      let details_html = details.length > 0 ? 
        `<small>${details.join('<br>')}</small>` : 
        '<small class="text-muted">No details</small>';

      html += `
        <tr style="border-left: 3px solid ${ot_req.actual_hours > 0 ? '#28a745' : '#6c757d'};">
          <td>
            <a href="/app/overtime-registration/${ot_req.request_name}" target="_blank" class="text-primary" style="text-decoration: none;">
              <strong>${ot_req.request_name}</strong>
            </a>
            ${ot_req.detail_name ? `<br><small class="text-muted">Detail: ${ot_req.detail_name}</small>` : ''}
          </td>
          <td>
            <span style="font-family: monospace; background: #f8f9fa; padding: 2px 6px; border-radius: 4px;">
              ${ot_req.planned_from} - ${ot_req.planned_to}
            </span>
          </td>
          <td><span class="badge badge-info">${ot_req.planned_hours}h</span></td>
          <td>${actual_hours_display}</td>
          <td>${status_badge}</td>
          <td>${details_html}</td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;

    // Enhanced summary with calculation explanation
    html += `
      <div class="overtime-summary" style="margin-top: 15px; padding: 12px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 6px; border-left: 4px solid #007bff;">
        <div style="margin-bottom: 8px;">
          <strong>📈 Calculation Summary:</strong>
        </div>
        <div class="row">
          <div class="col-md-6">
            <small>
              <strong> How it works:</strong><br>
              • Overtime = intersection of planned OT time vs actual check-in/out time<br>
              • Only actual worked overtime hours are counted<br>
              • Multiple OT registrations are summed up
            </small>
          </div>
          <div class="col-md-6">
            <small>
              <strong> Current Status:</strong><br>
              • Check-in: ${frm.doc.check_in ? moment(frm.doc.check_in).format('HH:mm') : 'Not set'}<br>
              • Check-out: ${frm.doc.check_out ? moment(frm.doc.check_out).format('HH:mm') : 'Not set'}<br>
              • Working Hours: ${frm.doc.working_hours || 0}h (including ${frm.doc.overtime_hours || 0}h OT)
            </small>
          </div>
        </div>
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

// Direct render function for connections (keeping existing function with minor updates)
function render_connections_html_direct(frm, checkins) {
  if (!checkins) {
    checkins = [];
  }

  let html = '';

  if (checkins.length === 0) {
    html = `
      <div class="alert alert-info" style="margin: 10px 0;">
        <h6>🔍 No Employee Check-ins found</h6>
        <p>No check-in records found for ${frm.doc.employee || 'this employee'} on ${frm.doc.attendance_date || 'this date'}.</p>
        <small class="text-muted">Debug info: Employee=${frm.doc.employee}, Date=${frm.doc.attendance_date}</small>
      </div>
    `;
  } else {
    // Header
    html += `
      <div class="connections-header" style="margin-bottom: 15px; padding: 10px; background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white; border-radius: 6px;">
        <h5 style="margin: 0; color: white;">🏃 Employee Check-ins (${checkins.length} records)</h5>
        <small style="color: rgba(255,255,255,0.9);">Check-in records for ${frm.doc.employee_name || frm.doc.employee} on ${frappe.datetime.str_to_user(frm.doc.attendance_date)}</small>
      </div>
    `;

    // Table
    html += `
      <div class="table-responsive">
        <table class="table table-bordered table-sm">
          <thead style="background-color: #f8f9fa;">
            <tr>
              <th style="width: 20%;"> Time</th>
              <th style="width: 25%;"> Check-in Record</th>
              <th style="width: 10%;"> Type</th>
              <th style="width: 15%;"> Device</th>
              <th style="width: 15%;"> Shift</th>
              <th style="width: 15%;"> Status</th>
            </tr>
          </thead>
          <tbody>
    `;

    checkins.forEach(function (checkin, index) {
      let time_formatted = checkin.time ? frappe.datetime.str_to_user(checkin.time) : 'N/A';
      let checkin_link = `<a href="/app/employee-checkin/${checkin.name}" target="_blank" class="text-primary" style="text-decoration: none;">${checkin.name}</a>`;
      let log_type_badge = checkin.log_type === 'IN' ?
        '<span class="badge badge-success"> IN</span>' :
        (checkin.log_type === 'OUT' ? '<span class="badge badge-warning"> OUT</span>' : '<span class="badge badge-secondary">?</span>');

      let linked_status = checkin.attendance === frm.doc.name ?
        '<span class="badge badge-success"> Linked</span>' :
        '<span class="badge badge-light"> Not Linked</span>';

      html += `
        <tr style="border-left: 3px solid ${checkin.log_type === 'IN' ? '#28a745' : '#ffc107'};">
          <td style="font-family: monospace;">${time_formatted}</td>
          <td>${checkin_link}</td>
          <td>${log_type_badge}</td>
          <td><code>${checkin.device_id || '-'}</code></td>
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
    let in_count = checkins.filter(c => c.log_type === 'IN').length;
    let out_count = checkins.filter(c => c.log_type === 'OUT').length;
    
    html += `
      <div class="connections-summary" style="margin-top: 10px; padding: 10px; background-color: #f8f9fa; border-radius: 4px; border-left: 4px solid #28a745;">
        <small>
          <strong> Summary:</strong> ${checkins.length} total check-ins 
          (${in_count} IN, ${out_count} OUT), ${linked_count} linked to this attendance record
        </small>
      </div>
    `;
  }

  // Set HTML to field6
  try {
    frm.set_df_property('connections_html', 'options', html);
    frm.refresh_field('connections_html');
  } catch (e) {
    console.error('Error setting connections HTML:', e);
  }
}