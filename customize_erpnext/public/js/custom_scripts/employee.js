// import apps/customize_erpnext/customize_erpnext/public/js/utilities.js

// Store original employee value to prevent naming series interference
window.original_employee_code = null;

// Ensure FingerprintScannerDialog is available
function ensureFingerprintModule() {
    return new Promise((resolve) => {
        if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
            resolve(true);
            return;
        }

        // Try to manually load the script if needed
        if (!document.querySelector('script[src*="fingerprint_scanner_dialog.js"]')) {
            const script = document.createElement('script');
            script.src = '/assets/customize_erpnext/js/fingerprint_scanner_dialog.js';
            document.head.appendChild(script);
        }

        // Try to load module if not available
        let attempts = 0;
        const maxAttempts = 15;  // Increased attempts

        const checkModule = () => {
            attempts++;

            if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
                resolve(true);
            } else if (attempts < maxAttempts) {
                setTimeout(checkModule, 200);
            } else {
                resolve(false);
            }
        };

        checkModule();
    });
}

frappe.ui.form.on('Employee', {
    refresh: function (frm) {
        // Add custom button for fingerprint scanning if not new record
        if (!frm.is_new() && frm.doc.name) {
            frm.add_custom_button(__('🔍 Scan Fingerprints'), async function () {
                // Show fingerprint scanner dialog with fixed employee
                const moduleReady = await ensureFingerprintModule();
                if (moduleReady) {
                    window.FingerprintScannerDialog.showForEmployee(frm.doc.name, frm.doc.employee_name);
                } else {
                    frappe.msgprint({
                        title: __('Module Loading Failed'),
                        message: __('Fingerprint Scanner module could not be loaded. Please refresh the page and try again.'),
                        indicator: 'red'
                    });
                }
            }, __('Actions'));
        }

        if (frm.is_new()) {
            // Auto-populate employee code and attendance device ID for new employees
            if (!frm.doc.employee || !frm.doc.employee.startsWith('TIQN-')) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_employee_code',
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('employee', r.message);
                            // Store the original value
                            window.original_employee_code = r.message;

                            // Update naming series to prevent duplicates
                            let employee_num = parseInt(r.message.replace('TIQN-', '')) - 1;
                            frappe.call({
                                method: 'customize_erpnext.api.employee.employee_utils.set_series',
                                args: {
                                    prefix: 'TIQN-',
                                    current_highest_id: employee_num
                                },
                                callback: function (series_r) {
                                    // Series updated successfully
                                }
                            });
                            // Auto-populated employee code successfully
                        }
                    }
                });

            } else {
                // Store existing value
                window.original_employee_code = frm.doc.employee;
            }

            if (!frm.doc.attendance_device_id) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_attendance_device_id',
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('attendance_device_id', r.message);
                        }
                    }
                });
            }
        } else {
            // For existing employees, store current value
            window.original_employee_code = frm.doc.employee;
        }
    },

    custom_scan_fingerprint: async function (frm) {
        // Handle custom button field click
        if (!frm.is_new() && frm.doc.name) {
            const moduleReady = await ensureFingerprintModule();
            if (moduleReady) {
                window.FingerprintScannerDialog.showForEmployee(frm.doc.name, frm.doc.employee_name);
            } else {
                frappe.msgprint({
                    title: __('Module Loading Failed'),
                    message: __('Fingerprint Scanner module could not be loaded. Please refresh the page and try again.'),
                    indicator: 'red'
                });
            }
        } else {
            frappe.msgprint({
                title: __('Save Required'),
                message: __('Please save the employee record first before scanning fingerprints.'),
                indicator: 'orange'
            });
        }
    },

    custom_sync_fingerprint_data_to_machine: function (frm) {
        // Handle sync fingerprint button click
        if (!frm.is_new() && frm.doc.name) {
            show_sync_fingerprint_dialog(frm.doc.name, frm.doc.employee_name);
        } else {
            frappe.msgprint({
                title: __('Save Required'),
                message: __('Please save the employee record first before syncing fingerprints.'),
                indicator: 'orange'
            });
        }
    },

    employee: function (frm) {
        // Store the employee value whenever it changes
        if (frm.doc.employee && frm.doc.employee.startsWith('TIQN-')) {
            window.original_employee_code = frm.doc.employee;
        }
    },

    before_save: function (frm) {
        // Ensure employee code follows TIQN-XXXX format
        if (frm.doc.employee && !frm.doc.employee.startsWith('TIQN-')) {
            frappe.msgprint(__('Employee code should follow TIQN-XXXX format'));
            frappe.validated = false;
            return;
        }

        // Check for duplicate employee code
        if (frm.doc.employee) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.check_duplicate_employee',
                args: {
                    employee_code: frm.doc.employee,
                    current_doc_name: frm.doc.name
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.exists) {
                        frappe.msgprint(__('Employee code {0} already exists in the system', [frm.doc.employee]));
                        frappe.validated = false;
                    }
                }
            });
        }

        // Check for duplicate attendance device ID
        if (frm.doc.attendance_device_id) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.check_duplicate_attendance_device_id',
                args: {
                    attendance_device_id: frm.doc.attendance_device_id,
                    current_doc_name: frm.doc.name
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.exists) {
                        frappe.msgprint(__('Attendance Device ID {0} already exists in the system', [frm.doc.attendance_device_id]));
                        frappe.validated = false;
                    }
                }
            });
        }

        // set employee_name = first_name + " " + midile_name + " " + last_name
        if (frm.doc.first_name && frm.doc.last_name) {
            frm.set_value('employee_name',
                [frm.doc.first_name, frm.doc.middle_name, frm.doc.last_name].filter(Boolean).join(' ')
            );
        }
        // check if employee_name icluding numbers throw error
        if (frm.doc.employee_name && /\d/.test(frm.doc.employee_name)) {
            frappe.msgprint(__('Employee name should not contain numbers'));
            frappe.validated = false;
        }

        // Validate maternity tracking date overlaps
        if (frm.doc.maternity_tracking && frm.doc.maternity_tracking.length > 1) {
            if (!validate_all_maternity_periods(frm)) {
                frappe.validated = false;
            }
        }
    },
});

// Maternity Tracking child table events
frappe.ui.form.on('Maternity Tracking', {
    type: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        // Auto-set apply_pregnant_benefit = 1 when type = 'Pregnant'
        if (row.type === 'Pregnant') {
            frappe.model.set_value(cdt, cdn, 'apply_pregnant_benefit', 1);
        } else {
            // Clear the field for other types since it's only relevant for Pregnant
            frappe.model.set_value(cdt, cdn, 'apply_pregnant_benefit', 0);
        }
    },
    
    from_date: function(frm, cdt, cdn) {
        validate_maternity_date_overlap(frm, cdt, cdn);
    },
    
    to_date: function(frm, cdt, cdn) {
        validate_maternity_date_overlap(frm, cdt, cdn);
        validate_date_sequence(frm, cdt, cdn);
    }
});

// Function to validate date sequence (from_date should be before to_date)
function validate_date_sequence(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    
    if (row.from_date && row.to_date) {
        let from_date = frappe.datetime.str_to_obj(row.from_date);
        let to_date = frappe.datetime.str_to_obj(row.to_date);
        
        if (from_date >= to_date) {
            frappe.msgprint({
                title: __('Invalid Date Range'),
                message: __('From Date must be earlier than To Date'),
                indicator: 'red'
            });
            frappe.model.set_value(cdt, cdn, 'to_date', '');
            return false;
        }
    }
    
    return true;
}

// Function to validate all maternity tracking periods on form save
function validate_all_maternity_periods(frm) {
    let maternity_tracking = frm.doc.maternity_tracking || [];
    let valid_periods = [];
    
    // First, validate each row for date sequence
    for (let i = 0; i < maternity_tracking.length; i++) {
        let row = maternity_tracking[i];
        
        if (!row.from_date || !row.to_date) {
            continue; // Skip incomplete rows
        }
        
        let from_date = frappe.datetime.str_to_obj(row.from_date);
        let to_date = frappe.datetime.str_to_obj(row.to_date);
        
        // Check date sequence
        if (from_date >= to_date) {
            frappe.msgprint({
                title: __('Invalid Date Range'),
                message: __('Row {0}: From Date must be earlier than To Date', [row.idx]),
                indicator: 'red'
            });
            return false;
        }
        
        valid_periods.push({
            idx: row.idx,
            type: row.type,
            from_date: from_date,
            to_date: to_date,
            from_date_str: frappe.datetime.str_to_user(row.from_date),
            to_date_str: frappe.datetime.str_to_user(row.to_date)
        });
    }
    
    // Check for overlapping periods
    for (let i = 0; i < valid_periods.length; i++) {
        for (let j = i + 1; j < valid_periods.length; j++) {
            let period1 = valid_periods[i];
            let period2 = valid_periods[j];
            
            // Check for overlap
            let has_overlap = (period1.from_date < period2.to_date && period1.to_date > period2.from_date);
            
            if (has_overlap) {
                frappe.msgprint({
                    title: __('Date Period Overlap Detected'),
                    message: __('Overlapping periods found:<br><br>Row {0}: {1} ({2} - {3})<br>Row {4}: {5} ({6} - {7})<br><br>Please adjust the dates to avoid overlapping periods.', [
                        period1.idx, period1.type, period1.from_date_str, period1.to_date_str,
                        period2.idx, period2.type, period2.from_date_str, period2.to_date_str
                    ]),
                    indicator: 'red'
                });
                return false;
            }
        }
    }
    
    return true;
}

// Function to validate overlapping date periods
function validate_maternity_date_overlap(frm, cdt, cdn) {
    let current_row = locals[cdt][cdn];
    
    // Only validate if both dates are filled
    if (!current_row.from_date || !current_row.to_date) {
        return;
    }
    
    let current_from = frappe.datetime.str_to_obj(current_row.from_date);
    let current_to = frappe.datetime.str_to_obj(current_row.to_date);
    
    // Validate date sequence first
    if (current_from >= current_to) {
        return; // Will be handled by validate_date_sequence
    }
    
    // Check for overlaps with other rows
    let maternity_tracking = frm.doc.maternity_tracking || [];
    let overlapping_rows = [];
    
    maternity_tracking.forEach(function(row) {
        // Skip current row and rows without both dates
        if (row.name === current_row.name || !row.from_date || !row.to_date) {
            return;
        }
        
        let row_from = frappe.datetime.str_to_obj(row.from_date);
        let row_to = frappe.datetime.str_to_obj(row.to_date);
        
        // Check for overlap: two periods overlap if one starts before the other ends
        let has_overlap = (current_from < row_to && current_to > row_from);
        
        if (has_overlap) {
            overlapping_rows.push({
                idx: row.idx,
                type: row.type,
                from_date: frappe.datetime.str_to_user(row.from_date),
                to_date: frappe.datetime.str_to_user(row.to_date)
            });
        }
    });
    
    if (overlapping_rows.length > 0) {
        let overlap_details = overlapping_rows.map(row => 
            `Row ${row.idx}: ${row.type} (${row.from_date} - ${row.to_date})`
        ).join('<br>');
        
        frappe.msgprint({
            title: __('Date Period Overlap Detected'),
            message: __('The current date period overlaps with existing records:<br><br>{0}<br><br>Please adjust the dates to avoid overlapping periods.', [overlap_details]),
            indicator: 'red'
        });
        
        // Clear both dates to force user to re-enter correct values
        frappe.model.set_value(cdt, cdn, 'from_date', '');
        frappe.model.set_value(cdt, cdn, 'to_date', '');
        
        return false;
    }
    
    return true;
}

function show_sync_fingerprint_dialog(employee_id, employee_name) {
    let d = new frappe.ui.Dialog({
        title: __('🔄 Sync Fingerprints to Machines - {0}', [employee_name || employee_id]),
        fields: [
            {
                fieldname: 'employee_info',
                fieldtype: 'HTML',
                options: `<div class="alert alert-info" style="margin-bottom: 15px;">
                    <div class="d-flex align-items-center">
                        <i class="fa fa-user" style="font-size: 20px; margin-right: 10px;"></i>
                        <div>
                            <strong>Employee:</strong> ${employee_name || employee_id}<br>
                            <small class="text-muted">This will sync all fingerprint data to enabled attendance machines</small>
                        </div>
                    </div>
                </div>`
            },
            {
                fieldname: 'machines_section',
                fieldtype: 'Section Break',
                label: __('Attendance Machines')
            },
            {
                fieldname: 'machines_list',
                fieldtype: 'HTML',
                options: '<div id="machines-list" style="background: #fff; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; margin-bottom: 15px;"><div class="text-center text-muted"><i class="fa fa-spinner fa-spin"></i> Loading machines...</div></div>'
            },
            {
                fieldname: 'sync_section',
                fieldtype: 'Section Break',
                label: __('Sync Progress')
            },
            {
                fieldname: 'sync_status',
                fieldtype: 'HTML',
                options: '<div id="sync-status" style="height: 200px; overflow-y: auto; padding: 15px; border-radius: 8px; background: #f8f9fa; border: 1px solid #dee2e6; font-family: monospace; font-size: 13px;"><div class="text-info">Ready to sync fingerprints to attendance machines...</div></div>'
            }
        ],
        primary_action_label: __('🚀 Start Sync'),
        primary_action: function () {
            start_sync_process(employee_id, employee_name, d);
        },
        secondary_action_label: __('🔄 Refresh Machines'),
        secondary_action: function () {
            load_machines_list();
        }
    });

    d.show();

    // Make dialog larger
    d.$wrapper.find('.modal-dialog').addClass('modal-xl');
    d.$wrapper.find('.modal-content').css({
        'border-radius': '12px',
        'box-shadow': '0 10px 30px rgba(0,0,0,0.2)'
    });
    d.$wrapper.find('.modal-header').css({
        'background': 'linear-gradient(135deg, #28a745 0%, #20c997 100%)',
        'color': 'white',
        'border-bottom': 'none',
        'border-radius': '12px 12px 0 0'
    });

    // Load machines list after dialog is shown
    setTimeout(() => {
        load_machines_list();
    }, 500);
}

function load_machines_list() {
    const machinesDiv = document.getElementById('machines-list');
    if (!machinesDiv) return;

    // Show loading
    machinesDiv.innerHTML = '<div class="text-center text-muted"><i class="fa fa-spinner fa-spin"></i> Checking attendance machines...</div>';

    frappe.call({
        method: 'customize_erpnext.api.utilities.get_enabled_attendance_machines',
        callback: function (r) {
            if (r.message && r.message.success) {
                display_machines_list(r.message);
            } else {
                machinesDiv.innerHTML = `<div class="alert alert-warning"><i class="fa fa-exclamation-triangle"></i> ${r.message.message || 'Failed to load machines'}</div>`;
            }
        },
        error: function (r) {
            machinesDiv.innerHTML = `<div class="alert alert-danger"><i class="fa fa-times"></i> Error loading machines: ${r.exc || 'Unknown error'}</div>`;
        }
    });
}

function display_machines_list(data) {
    const machinesDiv = document.getElementById('machines-list');
    if (!machinesDiv || !data.machines) return;

    const { machines, total_machines, online_machines, offline_machines } = data;

    if (machines.length === 0) {
        machinesDiv.innerHTML = `
            <div class="alert alert-warning">
                <i class="fa fa-exclamation-triangle me-2"></i>
                <strong>No master machines found.</strong> Please set enable & master_device at least one attendance machine to proceed.
            </div>
        `;
        return;
    }

    // Compact summary header
    let html = `
        <div class="d-flex justify-content-between align-items-center mb-3">
            <div class="d-flex align-items-center">
                <i class="fa fa-desktop text-primary me-2"></i>
                <strong>Attendance Machines (${total_machines})</strong>
            </div>
            <div class="d-flex align-items-center">
                <small class="badge badge-success me-1">🟢 ${online_machines}</small>
                <small class="badge badge-secondary me-1">🔴 ${offline_machines}</small>
                <small class="text-muted ms-2">${new Date().toLocaleTimeString()}</small>
            </div>
        </div>
    `;

    // Compact table format for many machines
    html += `
        <div class="table-responsive">
            <table class="table table-sm table-hover mb-2">
                <thead class="table-light">
                    <tr>
                        <th style="width: 30%"><i class="fa fa-tag me-1"></i>Name</th>
                        <th style="width: 35%"><i class="fa fa-network-wired me-1"></i>Address</th>
                        <th style="width: 20%"><i class="fa fa-signal me-1"></i>Status</th>
                        <th style="width: 15%"><i class="fa fa-clock-o me-1"></i>Response</th>
                    </tr>
                </thead>
                <tbody>
    `;

    machines.forEach(machine => {
        const statusIcon = machine.connection_status === 'online' ? '🟢' :
            machine.connection_status === 'offline' ? '🔴' : '⚠️';
        const statusColor = machine.connection_status === 'online' ? 'success' :
            machine.connection_status === 'offline' ? 'danger' : 'warning';
        const rowClass = machine.connection_status === 'online' ? 'table-success' :
            machine.connection_status === 'offline' ? 'table-danger' : 'table-warning';

        html += `
            <tr class="${rowClass}" style="border-left: 3px solid var(--bs-${statusColor});">
                <td>
                    <strong>${machine.device_name}</strong>
                    ${machine.location ? `<br><small class="text-muted">${machine.location}</small>` : ''}
                </td>
                <td>
                    <span class="font-monospace">${machine.ip_address}:${machine.port}</span>
                </td>
                <td>
                    <span class="badge badge-${statusColor}">${statusIcon} ${machine.connection_status.toUpperCase()}</span>
                </td>
                <td>
                    ${machine.response_time > 0 ?
                `<small class="text-muted">${machine.response_time}ms</small>` :
                '<small class="text-muted">-</small>'
            }
                </td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';

    // Compact status summary
    if (offline_machines > 0) {
        html += `<div class="alert alert-warning py-2 mb-2">
            <i class="fa fa-exclamation-triangle me-1"></i>
            <small><strong>${offline_machines}</strong> machine(s) offline. Sync will only work with online machines.</small>
        </div>`;
    } else {
        html += `<div class="alert alert-success py-2 mb-2">
            <i class="fa fa-check-circle me-1"></i>
            <small>All <strong>${online_machines}</strong> machines are online and ready for sync.</small>
        </div>`;
    }

    machinesDiv.innerHTML = html;
}

function start_sync_process(employee_id, employee_name, dialog) {
    // Disable sync button
    dialog.set_primary_action(__('Syncing...'), null);
    dialog.disable_primary_action();

    update_sync_status('🔄 Starting sync process...', 'info');
    update_sync_status(`📋 Employee: ${employee_name} (${employee_id})`, 'info');
    update_sync_status('🔍 Checking attendance machines and employee data...', 'info');

    frappe.call({
        method: 'customize_erpnext.api.utilities.sync_employee_fingerprint_to_machines',
        args: {
            employee_id: employee_id
        },
        callback: function (r) {
            if (r.message) {
                handle_sync_response(r.message, dialog);
            } else {
                update_sync_status('❌ No response from server', 'danger');
                reset_sync_button(dialog);
            }
        },
        error: function (r) {
            update_sync_status(`❌ Server error: ${r.exc || 'Unknown error'}`, 'danger');
            reset_sync_button(dialog);
        }
    });
}

function handle_sync_response(response, dialog) {
    if (response.success) {
        update_sync_status(`✅ ${response.message}`, 'success');

        if (response.summary) {
            const summary = response.summary;
            update_sync_status('', 'info');
            update_sync_status('📊 SYNC SUMMARY:', 'info');
            update_sync_status(`   👤 Employee: ${summary.employee_name}`, 'info');
            update_sync_status(`   🆔 Attendance ID: ${summary.attendance_device_id}`, 'info');
            update_sync_status(`   🔐 Privilege: ${summary.privilege}`, 'info');
            update_sync_status(`   🔑 Password: ${summary.password}`, 'info');
            update_sync_status(`   👆 Fingerprints: ${summary.fingerprints_count}`, 'info');
            update_sync_status(`   🖥️ Machines: ${summary.machines_success}/${summary.machines_total}`, 'info');
        }

        if (response.sync_results) {
            update_sync_status('', 'info');
            update_sync_status('🔧 MACHINE DETAILS:', 'info');

            response.sync_results.forEach(result => {
                const status = result.success ? '✅' : '❌';
                const color = result.success ? 'success' : 'danger';
                update_sync_status(`   ${status} ${result.machine} (${result.ip}): ${result.message}`, color);
            });
        }

        if (response.status === 'success') {
            frappe.show_alert({
                message: __('Fingerprints synced successfully to all machines!'),
                indicator: 'green'
            });
        } else if (response.status === 'partial') {
            frappe.show_alert({
                message: __('Fingerprints partially synced. Check details in dialog.'),
                indicator: 'orange'
            });
        }
    } else {
        update_sync_status(`❌ Sync failed: ${response.message}`, 'danger');
        frappe.show_alert({
            message: __('Sync failed: ' + response.message),
            indicator: 'red'
        });
    }

    reset_sync_button(dialog);

    // Refresh machines list after sync to show updated status
    setTimeout(() => {
        update_sync_status('🔄 Refreshing machines status...', 'info');
        load_machines_list();
    }, 2000);
}

function update_sync_status(message, type = 'info') {
    const statusDiv = document.getElementById('sync-status');
    if (statusDiv && message) {
        const timestamp = new Date().toLocaleTimeString();
        let textClass = 'text-info';

        if (type === 'success') {
            textClass = 'text-success';
        } else if (type === 'danger') {
            textClass = 'text-danger';
        } else if (type === 'warning') {
            textClass = 'text-warning';
        }

        const logEntry = `<div class="log-entry ${textClass} mb-1"><strong>[${timestamp}]</strong> ${message}</div>`;
        statusDiv.innerHTML += logEntry;

        // Scroll to bottom
        statusDiv.scrollTo({
            top: statusDiv.scrollHeight,
            behavior: 'smooth'
        });
    }
}

function reset_sync_button(dialog) {
    dialog.set_primary_action(__('🚀 Start Sync'), function () {
        // Clear previous status
        const statusDiv = document.getElementById('sync-status');
        if (statusDiv) {
            statusDiv.innerHTML = '<div class="text-info">Ready to sync fingerprints to attendance machines...</div>';
        }

        // Get employee data from dialog
        const employee_id = dialog.get_value('employee_id') || dialog.employee_id;
        const employee_name = dialog.get_value('employee_name') || dialog.employee_name;
        start_sync_process(employee_id, employee_name, dialog);
    });
    dialog.enable_primary_action();

    // Store employee data for reuse
    dialog.employee_id = arguments[0];
    dialog.employee_name = arguments[1];
}

function toProperCase(str) {
    if (!str) return str;

    let result = str.trim().toLowerCase();

    // First, handle regular word boundaries (spaces, punctuation)
    result = result.replace(/\b\w/g, function (char) {
        return char.toUpperCase();
    });

    // Special handling: ensure first non-number character is uppercase
    // This handles cases like "26ss" → "26Ss"
    result = result.replace(/^(\d*)([a-z])/, function (_, numbers, firstLetter) {
        return numbers + firstLetter.toUpperCase();
    });

    return result;
}