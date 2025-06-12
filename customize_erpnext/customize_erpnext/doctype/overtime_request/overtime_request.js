frappe.ui.form.on('Overtime Request', {
  refresh: function(frm) {
    // Add approval buttons based on status and user permissions
    if (frm.doc.docstatus === 1) { // Only for submitted documents
      add_approval_buttons(frm);
    }
  },

  ot_date: function(frm) {
    if (frm.doc.ot_date && frm.doc.ot_employees.length > 0) {
      adjust_rate_multipliers_for_date(frm);
    }
  },

  onload: function (frm) {
    if (frm.is_new() && !frm.doc.requested_by) {
      set_current_user_as_requester(frm);
    }
    
    // Set filters for approver fields
    set_approver_filters(frm);
  },

  ot_configuration: function (frm) {
    if (frm.doc.ot_configuration) {
      load_ot_configuration_data(frm);
    } else {
      clear_ot_level_options(frm);
    }
  },

  get_employees_button: function (frm) {
    if (!frm.doc.ot_configuration) {
      frappe.msgprint('Please select OT Configuration first');
      return;
    }
    if (!frm.doc.select_group) {
      frappe.msgprint('Please select a group first');
      return;
    }
    show_employee_selection_dialog(frm);
  }
});

// Set filters for approver fields
function set_approver_filters(frm) {
  frm.set_query("manager_approver", function() {
    return {
      query: "customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.get_factory_managers"
    };
  });

  frm.set_query("factory_manager_approver", function() {
    return {
      query: "customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.get_factory_managers"
    };
  });
}

// Load OT Configuration data
function load_ot_configuration_data(frm) {
  frappe.call({
    method: 'frappe.client.get',
    args: {
      doctype: 'Overtime Configuration',
      name: frm.doc.ot_configuration
    },
    callback: function (r) {
      if (r.message && r.message.overtime_levels) {
        frm._ot_config_data = r.message;
        setup_ot_level_dropdown(frm, r.message.overtime_levels);
        validate_existing_ot_levels(frm, r.message.overtime_levels);
      }
    }
  });
}

// Setup OT Level dropdown for child table
function setup_ot_level_dropdown(frm, overtime_levels) {
  const active_levels = overtime_levels.filter(level => level.is_active);
  const level_options = active_levels.map(level => level.level_name).join('\n');
  
  frm.fields_dict.ot_employees.grid.update_docfield_property('ot_level', 'options', level_options);
  
  if (frm.doc.ot_employees) {
    frm.doc.ot_employees.forEach(function(row) {
      frappe.meta.get_docfield('OT Employee Detail', 'ot_level', row.name).options = level_options;
    });
  }
  
  frm.refresh_field('ot_employees');
  
}

// Adjust rate multipliers for date
function adjust_rate_multipliers_for_date(frm) {
  if (!frm.doc.ot_date) return;
  
  let date_obj = frappe.datetime.str_to_obj(frm.doc.ot_date);
  let day_of_week = date_obj.getDay(); // 0 = Sunday
  let is_sunday = day_of_week === 0;
  
  let message = '';
  
  frm.doc.ot_employees.forEach(function(row) {
    let base_multiplier = get_base_multiplier_from_config(frm, row.ot_level);
    let adjusted_multiplier = base_multiplier;
    
    if (is_sunday) {
      adjusted_multiplier = 2.0;
      message = 'Weekend rate (x2.0) applied for Sunday';
    }
    
    frappe.model.set_value(row.doctype, row.name, 'rate_multiplier', adjusted_multiplier);
  });
  
  if (message) {
    frappe.show_alert({
      message: message,
      indicator: 'blue'
    });
  }
  
  frm.refresh_field('ot_employees');
  calculate_totals(frm);
}

function get_base_multiplier_from_config(frm, ot_level_name) {
  if (!frm._ot_config_data || !frm._ot_config_data.overtime_levels) {
    return 1.0;
  }
  
  const level = frm._ot_config_data.overtime_levels.find(l => l.level_name === ot_level_name);
  return level ? level.rate_multiplier : 1.0;
}

// Show employee selection dialog
function show_employee_selection_dialog(frm) {
  frappe.call({
    method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.show_employee_selection_dialog',
    args: {
      group_name: frm.doc.select_group,
      ot_configuration: frm.doc.ot_configuration
    },
    callback: function (r) {
      if (r.message && r.message.employees) {
        let employees = r.message.employees;
        let ot_levels = r.message.ot_levels;
        
        if (employees.length === 0) {
          frappe.msgprint('No employees found in selected group');
          return;
        }

        let dialog = new frappe.ui.Dialog({
          title: `Select Employees from Group: ${frm.doc.select_group}`,
          size: 'large',
          fields: [
            {
              fieldname: 'employees_html',
              fieldtype: 'HTML'
            },
            {
              fieldname: 'default_ot_level',
              fieldtype: 'Select',
              label: 'Default OT Level',
              options: ot_levels.map(level => level.level_name).join('\n'),
              default: ot_levels.length > 0 ? ot_levels[0].level_name : '',
              onchange: function() {
                update_hours_display(dialog, ot_levels, this.value);
              }
            },
            {
              fieldname: 'hours_info',
              fieldtype: 'HTML',
              label: 'Hours Information'
            }
          ],
          primary_action_label: 'Add Selected Employees',
          primary_action: function(values) {
            add_selected_employees_to_form(frm, dialog, employees, ot_levels, values);
          }
        });

        let html = `
          <div style="max-height: 400px; overflow-y: auto;">
            <table class="table table-bordered">
              <thead>
                <tr>
                  <th><input type="checkbox" id="select_all_employees"></th>
                  <th>Employee ID</th>
                  <th>Employee Name</th>
                  <th>Designation</th>
                  <th>Department</th>
                </tr>
              </thead>
              <tbody>
        `;

        employees.forEach(function(emp, index) {
          html += `
            <tr>
              <td><input type="checkbox" class="employee-checkbox" data-employee="${emp.name}" data-index="${index}"></td>
              <td>${emp.name}</td>
              <td>${emp.employee_name}</td>
              <td>${emp.designation || ''}</td>
              <td>${emp.department || ''}</td>
            </tr>
          `;
        });

        html += `
              </tbody>
            </table>
          </div>
        `;

        dialog.fields_dict.employees_html.$wrapper.html(html);

        dialog.fields_dict.employees_html.$wrapper.find('#select_all_employees').on('change', function() {
          let checked = $(this).is(':checked');
          dialog.fields_dict.employees_html.$wrapper.find('.employee-checkbox').prop('checked', checked);
        });

        if (ot_levels.length > 0) {
          update_hours_display(dialog, ot_levels, ot_levels[0].level_name);
        }

        dialog.show();
      }
    }
  });
}

// Update hours display
function update_hours_display(dialog, ot_levels, selected_level_name) {
  const selected_level = ot_levels.find(level => level.level_name === selected_level_name);
  
  if (selected_level) {
    let current_frm = cur_frm;
    let base_multiplier = selected_level.rate_multiplier;
    let adjusted_multiplier = base_multiplier;
    let rate_note = '';
    
    if (current_frm && current_frm.doc.ot_date) {
      adjusted_multiplier = get_adjusted_multiplier_for_date(current_frm.doc.ot_date, base_multiplier);
      let date_type = get_date_type(current_frm.doc.ot_date);
      
      if (date_type !== 'Weekday') {
        rate_note = `<br><strong>Adjusted for ${date_type}:</strong> x${adjusted_multiplier}`;
      }
    }
    
    let hours_info = `
      <div class="alert alert-info">
        <strong>Selected OT Level: ${selected_level.level_name}</strong><br>
        <strong>Base Rate Multiplier:</strong> x${base_multiplier}${rate_note}<br>
    `;
    
    if (selected_level.max_hours) {
      hours_info += `<strong>Max Hours:</strong> ${selected_level.max_hours} hours<br>`;
    }
    
    if (selected_level.default_hours) {
      hours_info += `<strong>Default Hours:</strong> ${selected_level.default_hours} hours<br>`;
    }
    
    if (selected_level.start_time && selected_level.end_time) {
      hours_info += `<strong>Time:</strong> ${selected_level.start_time} - ${selected_level.end_time}<br>`;
    }
    
    hours_info += `</div>`;
    
    dialog.fields_dict.hours_info.$wrapper.html(hours_info);
  }
}

// Add selected employees to form
function add_selected_employees_to_form(frm, dialog, employees, ot_levels, values) {
  let selected_checkboxes = dialog.fields_dict.employees_html.$wrapper.find('.employee-checkbox:checked');
  
  if (selected_checkboxes.length === 0) {
    frappe.msgprint('Please select at least one employee');
    return;
  }

  let selected_ot_level = ot_levels.find(level => level.level_name === values.default_ot_level);

  selected_checkboxes.each(function() {
    let employee_id = $(this).data('employee');
    let employee_index = $(this).data('index');
    let employee = employees[employee_index];

    let exists = frm.doc.ot_employees.some(row => row.employee === employee_id);
    if (exists) {
      return;
    }

    let row = frm.add_child('ot_employees');
    row.employee = employee.name;
    row.employee_name = employee.employee_name;
    row.designation = employee.designation;
    row.department = employee.department;
    
    if (selected_ot_level) {
      row.ot_level = selected_ot_level.level_name;
      
      let base_multiplier = selected_ot_level.rate_multiplier;
      let adjusted_multiplier = get_adjusted_multiplier_for_date(frm.doc.ot_date, base_multiplier);
      row.rate_multiplier = adjusted_multiplier;
      
      row.planned_hours = selected_ot_level.default_hours || selected_ot_level.max_hours || 8.0;
      
      if (selected_ot_level.start_time) {
        row.start_time = selected_ot_level.start_time;
      }
      if (selected_ot_level.end_time) {
        row.end_time = selected_ot_level.end_time;
      }
    }
  });

  frm.refresh_field('ot_employees');
  calculate_totals(frm);
  
  let date_type = get_date_type(frm.doc.ot_date);
  if (date_type !== 'Weekday') {
    frappe.show_alert({
      message: `${selected_checkboxes.length} employees added with ${date_type} rate applied`,
      indicator: 'blue'
    });
  } else {
    frappe.show_alert({
      message: `${selected_checkboxes.length} employees added successfully`,
      indicator: 'green'
    });
  }

  dialog.hide();
}

// Helper functions
function get_adjusted_multiplier_for_date(ot_date, base_multiplier) {
  if (!ot_date) return base_multiplier;
  
  let date_obj = frappe.datetime.str_to_obj(ot_date);
  let day_of_week = date_obj.getDay();
  
  if (day_of_week === 0) { // Sunday
    return 2.0;
  }
  
  return base_multiplier;
}

function get_date_type(ot_date) {
  if (!ot_date) return 'Weekday';
  
  let date_obj = frappe.datetime.str_to_obj(ot_date);
  let day_of_week = date_obj.getDay();
  
  if (day_of_week === 0) {
    return 'Weekend (Sunday)';
  }
  
  return 'Weekday';
}

// Clear OT level options
function clear_ot_level_options(frm) {
  frm.fields_dict.ot_employees.grid.update_docfield_property('ot_level', 'options', '');
  frm.refresh_field('ot_employees');
  frm._ot_config_data = null;
  
}

// Validate existing OT levels
function validate_existing_ot_levels(frm, overtime_levels) {
  const active_level_names = overtime_levels
    .filter(level => level.is_active)
    .map(level => level.level_name);

  let has_invalid = false;
  frm.doc.ot_employees.forEach(row => {
    if (row.ot_level && !active_level_names.includes(row.ot_level)) {
      frappe.model.set_value(row.doctype, row.name, 'ot_level', '');
      has_invalid = true;
    }
  });

  if (has_invalid) {
    frappe.show_alert({
      message: 'Some OT levels were cleared due to configuration change',
      indicator: 'orange'
    });
  }
}

// Set current user as requester
function set_current_user_as_requester(frm) {
  frappe.call({
    method: 'frappe.client.get_value',
    args: {
      doctype: 'Employee',
      filters: { 'user_id': frappe.session.user },
      fieldname: 'name'
    },
    callback: function (r) {
      if (r.message && r.message.name) {
        frm.set_value('requested_by', r.message.name);
      }
    }
  });
}

// OT Employee Detail events
frappe.ui.form.on('OT Employee Detail', {
  ot_level: function (frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.ot_level && frm._ot_config_data) {
      set_ot_level_details(frm, cdt, cdn, row.ot_level);
    }
  },

  planned_hours: function (frm) {
    calculate_totals(frm);
  },

  ot_employees_remove: function (frm) {
    calculate_totals(frm);
  },

  ot_employees_add: function (frm, cdt, cdn) {
    setTimeout(() => {
      if (frm.doc.ot_configuration && frm._ot_config_data) {
        setup_ot_level_dropdown(frm, frm._ot_config_data.overtime_levels);
      }
    }, 300);
  }
});

// Set OT level details
function set_ot_level_details(frm, cdt, cdn, selected_level_name) {
  if (!frm._ot_config_data || !frm._ot_config_data.overtime_levels) return;

  const selected_level = frm._ot_config_data.overtime_levels.find(level =>
    level.level_name === selected_level_name && level.is_active
  );

  if (selected_level) {
    let base_multiplier = selected_level.rate_multiplier;
    let adjusted_multiplier = get_adjusted_multiplier_for_date(frm.doc.ot_date, base_multiplier);
    
    frappe.model.set_value(cdt, cdn, 'rate_multiplier', adjusted_multiplier);

    if (selected_level.start_time) {
      frappe.model.set_value(cdt, cdn, 'start_time', selected_level.start_time);
    }
    if (selected_level.end_time) {
      frappe.model.set_value(cdt, cdn, 'end_time', selected_level.end_time);
    }
    
    if (selected_level.default_hours) {
      frappe.model.set_value(cdt, cdn, 'planned_hours', selected_level.default_hours);
    } else if (selected_level.max_hours) {
      frappe.model.set_value(cdt, cdn, 'planned_hours', selected_level.max_hours);
    }

    setTimeout(() => calculate_totals(frm), 200);
    
  }
}

// Calculate totals
function calculate_totals(frm) {
  let total_employees = frm.doc.ot_employees.length;
  let total_hours = 0;

  frm.doc.ot_employees.forEach(function (row) {
    if (row.planned_hours) {
      total_hours += row.planned_hours;
    }
  });

  frm.set_value('total_employees', total_employees);
  frm.set_value('total_hours', total_hours);
}

// Approval buttons functions
function add_approval_buttons(frm) {
  // Get current user's employee ID
  frappe.call({
    method: 'frappe.client.get_value',
    args: {
      doctype: 'Employee',
      filters: { 'user_id': frappe.session.user },
      fieldname: 'name'
    },
    callback: function (r) {
      if (r.message && r.message.name) {
        let current_user_employee = r.message.name;
        
        // Manager Approval Button
        if (frm.doc.status === "Pending Manager Approval" && 
            frm.doc.manager_approver === current_user_employee) {
          
          frm.add_custom_button(__('Approve (Manager)'), function() {
            approve_request(frm, 'manager');
          }, __('Actions')).addClass('btn-success');
          
          frm.add_custom_button(__('Reject (Manager)'), function() {
            reject_request(frm, 'manager');
          }, __('Actions')).addClass('btn-danger');
        }
        
        // Factory Manager Approval Button
        if (frm.doc.status === "Pending Factory Manager Approval" && 
            frm.doc.factory_manager_approver === current_user_employee) {
          
          frm.add_custom_button(__('Approve (Factory Manager)'), function() {
            approve_request(frm, 'factory_manager');
          }, __('Actions')).addClass('btn-success');
          
          frm.add_custom_button(__('Reject (Factory Manager)'), function() {
            reject_request(frm, 'factory_manager');
          }, __('Actions')).addClass('btn-danger');
        }
      }
    }
  });
}

function approve_request(frm, approval_type) {
  frappe.confirm(
    `Are you sure you want to approve this overtime request?`,
    function() {
      frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.approve_overtime_request',
        args: {
          name: frm.doc.name,
          approval_type: approval_type,
          comments: ''
        },
        callback: function(r) {
          if (!r.exc) {
            frm.reload_doc();
            frappe.show_alert({
              message: 'Request approved successfully',
              indicator: 'green'
            });
          }
        }
      });
    }
  );
}

function reject_request(frm, rejection_type) {
  frappe.prompt([
    {
      label: 'Rejection Comments',
      fieldname: 'comments',
      fieldtype: 'Text',
      reqd: 1
    }
  ], function(values) {
    frappe.call({
      method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.reject_overtime_request',
      args: {
        name: frm.doc.name,
        rejection_type: rejection_type,
        comments: values.comments
      },
      callback: function(r) {
        if (!r.exc) {
          frm.reload_doc();
          frappe.show_alert({
            message: 'Request rejected successfully',
            indicator: 'red'
          });
        }
      }
    });
  }, 'Reject Overtime Request', 'Reject');
}
