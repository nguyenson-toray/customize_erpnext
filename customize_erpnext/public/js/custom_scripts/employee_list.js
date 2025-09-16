console.log('Employee list customization loaded successfully');
// import apps/customize_erpnext/customize_erpnext/public/js/shared_fingerprint_sync.js

frappe.listview_settings['Employee'] = {
    onload: function (listview) {
        console.log('Employee listview onload triggered');
        // Add individual menu items under Actions
        listview.page.add_menu_item(__('Scan Fingerprint'), function () {
            show_get_fingerprint_dialog();
        });

        listview.page.add_menu_item(__('Sync Fingerprint From Attendance Machines To ERP'), function () {
            show_sync_fingerprint_from_erp_to_attendance_machine_dialog();
        });
        listview.page.add_menu_item(__('Sync Fingerprint From ERP To Attendance Machines'), function () {
            show_multi_employee_sync_dialog(listview);
        });
    }
};

function show_get_fingerprint_dialog() {
    let d = new frappe.ui.Dialog({
        title: __('🔍 Fingerprint Scanner'),
        fields: [
            {
                fieldname: 'employee_section',
                fieldtype: 'Section Break',
                label: __('Select Employee')
            },
            {
                fieldname: 'employee',
                fieldtype: 'Link',
                label: __('Employee'),
                options: 'Employee',
                reqd: 1,
                get_query: function () {
                    return {
                        filters: {
                            status: 'Active'
                        },
                        order_by: 'employee desc'
                    };
                },
                change: function () {
                    const employee_id = this.get_value();
                    if (employee_id) {
                        frappe.call({
                            method: 'customize_erpnext.api.utilities.get_employee_fingerprints_status',
                            args: { employee_id: employee_id },
                            callback: function (r) {
                                if (r.message && r.message.success) {
                                    update_finger_status_display(r.message.existing_fingers);
                                } else {
                                    update_finger_status_display([]);
                                }
                            }
                        });
                    } else {
                        update_finger_status_display([]);
                    }
                }
            },
            {
                fieldname: 'column_break_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'finger_selection',
                fieldtype: 'Select',
                label: __('Select Finger'),
                options: [
                    '',
                    __('Left Thumb'),
                    __('Left Index'),
                    __('Left Middle'),
                    __('Left Ring'),
                    __('Left Little'),
                    __('Right Thumb'),
                    __('Right Index'),
                    __('Right Middle'),
                    __('Right Ring'),
                    __('Right Little')
                ],
                reqd: 1,
                description: __('Choose which finger to scan'),
                change: function () {
                    const employee_id = d.get_value('employee');
                    const finger_selection_name = this.get_value();

                    if (!employee_id) {
                        frappe.msgprint({
                            title: __('⚠️ Employee Required'),
                            message: __('Please select an Employee first.'),
                            indicator: 'orange'
                        });
                        d.set_value('finger_selection', '');
                        return;
                    }

                    if (finger_selection_name) {
                        const finger_map = {
                            'Left Thumb': 0, 'Left Index': 1, 'Left Middle': 2, 'Left Ring': 3, 'Left Little': 4,
                            'Right Thumb': 5, 'Right Index': 6, 'Right Middle': 7, 'Right Ring': 8, 'Right Little': 9
                        };
                        const selected_finger_index = finger_map[finger_selection_name];

                        frappe.call({
                            method: 'customize_erpnext.api.utilities.get_employee_fingerprints_status',
                            args: { employee_id: employee_id },
                            callback: function (r) {
                                if (r.message && r.message.success) {
                                    const existing_fingers = r.message.existing_fingers;
                                    if (existing_fingers.includes(selected_finger_index)) {
                                        frappe.confirm(
                                            __('🔄 This finger already has fingerprint data. Replace it?'),
                                            function () {
                                                // User confirmed to replace
                                            },
                                            function () {
                                                d.set_value('finger_selection', '');
                                            }
                                        );
                                    }
                                }
                            }
                        });
                    }
                }
            },
            {
                fieldname: 'scan_section',
                fieldtype: 'Section Break',
                label: __('Fingerprint Status')
            },
            {
                fieldname: 'finger_status_display',
                fieldtype: 'HTML',
                options: '<div id="finger-status-display" style="padding: 15px; border-radius: 8px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border: 1px solid #dee2e6; margin-bottom: 15px;"><div class="d-flex align-items-center mb-3"><i class="fa fa-hand-paper-o" style="font-size: 24px; color: #6c757d; margin-right: 10px;"></i><h6 class="mb-0 text-muted">Fingerprint Status Overview</h6></div><div id="finger-grid" class="row"></div></div>'
            },
            {
                fieldname: 'column_break_2',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'scan_status',
                fieldtype: 'HTML',
                options: '<div id="scan-status-container" style="background: #fff; border: 2px solid #e9ecef; border-radius: 8px; padding: 15px;"><div class="d-flex align-items-center mb-3"><i class="fa fa-desktop" style="font-size: 20px; color: #007bff; margin-right: 10px;"></i><h6 class="mb-0">Scanner Activity</h6></div><div id="scan-status" style="height: 180px; overflow-y: auto; padding: 10px; border-radius: 6px; background: #f8f9fa; font-family: \'Monaco\', \'Menlo\', \'Ubuntu Mono\', monospace; font-size: 13px; line-height: 1.4;"><div class="log-entry text-info"><strong>[' + new Date().toLocaleTimeString() + ']</strong> 🟢 Ready to scan fingerprints</div></div></div>'
            },
            {
                fieldname: 'history_section',
                fieldtype: 'Section Break',
                label: __('Recent Activity')
            },
            {
                fieldname: 'scan_history',
                fieldtype: 'HTML',
                options: '<div id="scan-history-container" style="background: #fff; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px;"><div class="d-flex align-items-center justify-content-between mb-3"><div class="d-flex align-items-center"><i class="fa fa-history" style="font-size: 18px; color: #28a745; margin-right: 8px;"></i><h6 class="mb-0">Recent Scans</h6></div><small class="text-muted">Last 10 scans</small></div><div id="scan-list" style="max-height: 120px; overflow-y: auto;"><div class="text-center text-muted py-3"><i class="fa fa-clock-o"></i> No scans yet</div></div></div>'
            }
        ],
        primary_action_label: __('🔍 Start Scan'),
        primary_action(values) {
            if (!values.employee || !values.finger_selection) {
                frappe.msgprint({
                    title: __('⚠️ Missing Information'),
                    message: __('Please select both Employee and Finger before scanning.'),
                    indicator: 'orange'
                });
                return;
            }
            start_fingerprint_capture(values, d);
        },
        secondary_action_label: __('🔄 Reset'),
        secondary_action() {
            d.set_value('employee', '');
            d.set_value('finger_selection', '');
            update_scan_status(__('🔄 Fields cleared - Ready for new scan'), 'info');
            update_finger_status_display([]);
        }
    });

    d.show();
    update_finger_status_display([]); // Initialize finger status display

    // Make dialog larger and add custom styling
    d.$wrapper.find('.modal-dialog').addClass('modal-xl');
    d.$wrapper.find('.modal-content').css({
        'border-radius': '12px',
        'box-shadow': '0 10px 30px rgba(0,0,0,0.2)'
    });
    d.$wrapper.find('.modal-header').css({
        'background': 'linear-gradient(135deg, #007bff 0%, #0056b3 100%)',
        'color': 'white',
        'border-bottom': 'none',
        'border-radius': '12px 12px 0 0'
    });

    // Initialize scan status
    window.scan_dialog = d;
    window.scan_count = 0;
}

function update_finger_status_display(existing_fingers) {
    console.log('update_finger_status_display called with:', existing_fingers);
    const fingerGrid = document.getElementById('finger-grid');
    console.log('fingerGrid element found:', !!fingerGrid);
    
    if (fingerGrid) {
        // Ensure existing_fingers is an array
        existing_fingers = existing_fingers || [];
        if (!Array.isArray(existing_fingers)) {
            console.warn('existing_fingers is not an array:', existing_fingers);
            existing_fingers = [];
        }
        
        const finger_map_reverse = {
            0: 'Left Thumb', 1: 'Left Index', 2: 'Left Middle', 3: 'Left Ring', 4: 'Left Little',
            5: 'Right Thumb', 6: 'Right Index', 7: 'Right Middle', 8: 'Right Ring', 9: 'Right Little'
        };

        let grid_html = '';

        // Left hand
        grid_html += '<div class="col-md-6"><div class="card border-0 shadow-sm mb-3"><div class="card-header bg-primary text-white text-center py-2"><i class="fa fa-hand-o-left"></i> Left Hand</div><div class="card-body p-2">';
        for (let i = 0; i < 5; i++) {
            const has_data = existing_fingers.includes(i);
            const status_icon = has_data ? '✅' : '⭕';
            const status_color = has_data ? 'success' : 'secondary';
            grid_html += `<div class="d-flex justify-content-between align-items-center py-1 px-2 border-bottom"><small><strong>${finger_map_reverse[i]}</strong></small><span class="badge badge-${status_color}">${status_icon} ${has_data ? 'Enrolled' : 'Empty'}</span></div>`;
        }
        grid_html += '</div></div></div>';

        // Right hand  
        grid_html += '<div class="col-md-6"><div class="card border-0 shadow-sm mb-3"><div class="card-header bg-info text-white text-center py-2"><i class="fa fa-hand-o-right"></i> Right Hand</div><div class="card-body p-2">';
        for (let i = 5; i < 10; i++) {
            const has_data = existing_fingers.includes(i);
            const status_icon = has_data ? '✅' : '⭕';
            const status_color = has_data ? 'success' : 'secondary';
            grid_html += `<div class="d-flex justify-content-between align-items-center py-1 px-2 border-bottom"><small><strong>${finger_map_reverse[i]}</strong></small><span class="badge badge-${status_color}">${status_icon} ${has_data ? 'Enrolled' : 'Empty'}</span></div>`;
        }
        grid_html += '</div></div></div>';

        fingerGrid.innerHTML = grid_html;
        console.log('Fingerprint status display updated successfully');
    } else {
        console.error('finger-grid element not found in DOM');
        // Try to find it after a short delay
        setTimeout(() => {
            const delayedGrid = document.getElementById('finger-grid');
            if (delayedGrid) {
                console.log('Found finger-grid after delay, retrying...');
                update_finger_status_display(existing_fingers);
            }
        }, 500);
    }
}

function start_fingerprint_capture(values, dialog) {
    // Get finger index from selection
    const finger_map = {
        'Left Thumb': 0, 'Left Index': 1, 'Left Middle': 2, 'Left Ring': 3, 'Left Little': 4,
        'Right Thumb': 5, 'Right Index': 6, 'Right Middle': 7, 'Right Ring': 8, 'Right Little': 9
    };

    const finger_index = finger_map[values.finger_selection];

    // Initialize scan attempt counter if not exists
    if (!window.scan_attempts) {
        window.scan_attempts = {};
    }
    
    // Reset attempt counter for this finger
    const attempt_key = `${values.employee}_${finger_index}`;
    window.scan_attempts[attempt_key] = 0;

    // Keep dialog open but disable scan button during process
    dialog.set_primary_action(__('Scanning...'), null);
    dialog.disable_primary_action();

    // Update status in dialog with scan attempt indicator
    update_scan_status(__('🔍 Starting fingerprint scan process...'), 'info');
    update_scan_status(__('📡 Checking Desktop Bridge connection...'), 'info');
    update_scan_status(__('📋 Process: LẦN 1 → LẦN 2 → LẦN 3 → Merge → Complete'), 'info');

    // Step 1: Check desktop bridge availability
    check_desktop_bridge_status(function (bridgeAvailable) {
        if (!bridgeAvailable) {
            update_scan_status(__('❌ Desktop Bridge connection failed! Please restart the application.'), 'danger');
            reset_scan_button(dialog);
            return;
        }

        update_scan_status(__('✅ Desktop Bridge connected. Initializing scanner...'), 'success');

        // Step 2: Initialize scanner via desktop bridge
        initialize_scanner_via_bridge(function (success, message) {
            if (success) {
                update_scan_status(__('🔍 Scanner ready! Please place finger on scanner...'), 'success');

                // Step 3: Capture fingerprint
                setTimeout(() => {
                    capture_fingerprint_data(values.employee, finger_index, values.finger_selection, dialog);
                }, 1000);

            } else {
                update_scan_status(__('❌ Scanner initialization failed: ' + message), 'danger');
                reset_scan_button(dialog);
            }
        });
    });

    function capture_fingerprint_data(employee_id, finger_index, finger_name, dialog) {
        update_scan_status(__('🔄 Starting fingerprint enrollment process...'), 'info');

        // Use direct enrollment via bridge (single API call with real-time updates)
        capture_fingerprint_via_bridge(employee_id, finger_index, function (success, data, message) {
            if (success) {
                const final_template_data = data.template_data;
                const final_template_size = data.template_size;
                const quality_score = data.quality_score || data.quality || 0;

                update_scan_status(`✅ Fingerprint enrollment completed! (${final_template_size} bytes, Quality: ${quality_score})`, 'success');

                // Save to ERPNext database
                save_fingerprint_to_erpnext(employee_id, finger_index, final_template_data, quality_score, function (saveSuccess, fingerprintId) {
                    if (saveSuccess) {
                        update_scan_status(__('💾 Fingerprint saved to database successfully'), 'success');
                        add_scan_to_history(employee_id, finger_name, final_template_size, 'success');

                        // Refresh finger status display
                        frappe.call({
                            method: 'customize_erpnext.api.utilities.get_employee_fingerprints_status',
                            args: { employee_id: employee_id },
                            callback: function (r) {
                                if (r.message && r.message.success) {
                                    update_finger_status_display(r.message.existing_fingers);
                                }
                            }
                        });

                        setTimeout(() => {
                            dialog.set_value('finger_selection', '');
                            update_scan_status(__('🟢 Ready for next scan'), 'info');
                            reset_scan_button(dialog);
                            // Reset attempt counter on successful scan
                            window.scan_attempts[attempt_key] = 0;
                        }, 1500);  // Reduced delay
                    } else {
                        update_scan_status(__('❌ Failed to save to database'), 'danger');
                        add_scan_to_history(employee_id, finger_name, 0, 'failed');
                        reset_scan_button(dialog);
                    }
                    disconnect_scanner_via_bridge();
                });
            } else {
                update_scan_status(`❌ Enrollment failed: ${message}`, 'danger');
                add_scan_to_history(employee_id, finger_name, 0, 'failed');
                reset_scan_button(dialog);
                disconnect_scanner_via_bridge();
            }
        });
    }
}

function update_scan_status(message, type = 'info') {
    const statusDiv = document.getElementById('scan-status');
    if (statusDiv && message !== '') {
        const timestamp = new Date().toLocaleTimeString();
        let textClass = 'text-info';
        let icon = '🔵';

        if (type === 'success') {
            textClass = 'text-success';
            icon = '✅';
        } else if (type === 'danger') {
            textClass = 'text-danger';
            icon = '❌';
        } else if (type === 'warning') {
            textClass = 'text-warning';
            icon = '⚠️';
        }

        // Check if message contains HTML (attempt number display)
        let logEntry;
        if (message.includes('<div style=')) {
            // Special handling for HTML content (attempt display)
            logEntry = `<div class="log-entry mb-1">${message}</div>`;
        } else {
            // Regular text message
            logEntry = `<div class="log-entry ${textClass} mb-1"><strong>[${timestamp}]</strong> ${icon} ${message}</div>`;
        }
        
        statusDiv.innerHTML += logEntry;

        // Keep only last 15 log entries
        const logEntries = statusDiv.querySelectorAll('.log-entry');
        if (logEntries.length > 15) {
            logEntries[0].remove();
        }

        // Scroll to bottom with smooth animation
        statusDiv.scrollTo({
            top: statusDiv.scrollHeight,
            behavior: 'smooth'
        });
    }
}

function reset_scan_button(dialog) {
    dialog.set_primary_action(__('🔍 Start Scan'), function (values) {
        // Reset attempt counter when starting fresh scan
        if (window.scan_attempts && values.employee && values.finger_selection) {
            const finger_map = {
                'Left Thumb': 0, 'Left Index': 1, 'Left Middle': 2, 'Left Ring': 3, 'Left Little': 4,
                'Right Thumb': 5, 'Right Index': 6, 'Right Middle': 7, 'Right Ring': 8, 'Right Little': 9
            };
            const finger_index = finger_map[values.finger_selection];
            const attempt_key = `${values.employee}_${finger_index}`;
            window.scan_attempts[attempt_key] = 0;
        }
        start_fingerprint_capture(values, dialog);
    });
    dialog.enable_primary_action();
}

function add_scan_to_history(employee_id, finger_name, template_size, status) {
    window.scan_count++;
    const scanList = document.getElementById('scan-list');
    if (scanList) {
        // Clear "No scans yet" message
        if (window.scan_count === 1) {
            scanList.innerHTML = '';
        }

        const timestamp = new Date().toLocaleTimeString();
        let statusIcon = '';
        let statusClass = '';
        let bgClass = '';

        if (status === 'success') {
            statusIcon = '✅';
            statusClass = 'text-success';
            bgClass = 'alert-success';
        } else if (status === 'warning') {
            statusIcon = '⚠️';
            statusClass = 'text-warning';
            bgClass = 'alert-warning';
        } else {
            statusIcon = '❌';
            statusClass = 'text-danger';
            bgClass = 'alert-danger';
        }

        const scanEntry = `
            <div class="scan-entry ${bgClass} border-0 rounded p-2 mb-2" style="background-color: rgba(var(--bs-${status === 'success' ? 'success' : status === 'warning' ? 'warning' : 'danger'}-rgb), 0.1);">
                <div class="d-flex justify-content-between align-items-center">
                    <div class="d-flex align-items-center">
                        <span class="badge badge-primary me-2">#${window.scan_count}</span>
                        <small><strong>${employee_id}</strong> - ${finger_name}</small>
                    </div>
                    <small class="${statusClass}">${statusIcon} ${status.toUpperCase()}</small>
                </div>
                <div class="d-flex justify-content-between mt-1">
                    <small class="text-muted">${timestamp}</small>
                    ${template_size > 0 ? `<small class="text-muted">${template_size} bytes</small>` : ''}
                </div>
            </div>
        `;

        scanList.innerHTML = scanEntry + scanList.innerHTML;

        // Keep only last 8 scans
        const entries = scanList.querySelectorAll('.scan-entry');
        if (entries.length > 8) {
            entries[entries.length - 1].remove();
        }
    }
}

// Desktop Bridge API Functions
const DESKTOP_BRIDGE_URL = 'http://127.0.0.1:8080/api';

function check_desktop_bridge_status(callback) {
    // Use AbortController for better timeout handling
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);  // Reduced from 5s to 3s

    fetch(`${DESKTOP_BRIDGE_URL}/test`, {
        method: 'GET',
        signal: controller.signal
    })
        .then(response => {
            clearTimeout(timeoutId);
            return response.json();
        })
        .then(data => {
            callback(data.success);
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.error('Desktop bridge not available:', error);
            callback(false);
        });
}

function initialize_scanner_via_bridge(callback) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);  // Timeout for scanner init

    fetch(`${DESKTOP_BRIDGE_URL}/scanner/initialize`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        signal: controller.signal
    })
        .then(response => {
            clearTimeout(timeoutId);
            return response.json();
        })
        .then(data => {
            callback(data.success, data.message);
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.error('Error initializing scanner:', error);
            callback(false, 'Scanner initialization timeout or network error');
        });
}

function capture_fingerprint_via_bridge(employee_id, finger_index, callback) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);  // 30s for fingerprint capture

    // Start polling logs for real-time updates BEFORE making the capture request
    const pollInterval = start_log_polling();
    
    // Small delay to ensure polling is active before bridge starts logging
    setTimeout(() => {
        fetch(`${DESKTOP_BRIDGE_URL}/fingerprint/capture`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                employee_id: employee_id,
                finger_index: finger_index
            }),
            signal: controller.signal
        })
            .then(response => {
                clearTimeout(timeoutId);
                return response.json();
            })
            .then(data => {
                // Stop polling when capture is complete
                stop_log_polling(pollInterval);
                callback(data.success, data, data.message);
            })
            .catch(error => {
                clearTimeout(timeoutId);
                console.error('Error capturing fingerprint:', error);
                // Stop polling on error
                stop_log_polling(pollInterval);
                callback(false, null, 'Fingerprint capture timeout or network error');
            });
    }, 300);  // 300ms delay to ensure log polling is active
}

function start_log_polling() {
    // Start polling from 2 seconds ago to catch any logs that might have been generated
    let startTime = new Date();
    startTime.setSeconds(startTime.getSeconds() - 2);
    let lastTimestamp = startTime.toTimeString().substring(0, 8);
    
    const pollLogs = () => {
        fetch(`${DESKTOP_BRIDGE_URL}/logs/since?since=${lastTimestamp}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.logs && data.logs.length > 0) {
                    data.logs.forEach(log => {
                        // Display bridge logs in Scanner Activity
                        if (log.message.includes('LẦN') || 
                            log.message.includes('Quality') || 
                            log.message.includes('Scan completed') ||
                            log.message.includes('ENROLLMENT COMPLETED') ||
                            log.message.includes('Waiting for fingerprint') ||
                            log.message.includes('Ready for scan') ||
                            log.message.includes('OK') || 
                            log.message.includes('FAIL')) {
                            
                            let logType = 'info';
                            if (log.level === 'success') logType = 'success';
                            else if (log.level === 'error') logType = 'danger';
                            else if (log.level === 'warning') logType = 'warning';
                            else if (log.level === 'in_progress') logType = 'warning';
                            else if (log.level === 'waiting') logType = 'info';
                            
                            // Style LẦN messages differently
                            let displayMessage = log.message;
                            if (log.message.match(/^(🔄|✅|❌|⏳)\s*LẦN\s*\d+/)) {
                                // This is a scan attempt indicator
                                displayMessage = `<div style="text-align: center; font-size: 2em; font-weight: bold; margin: 10px 0;">${log.message}</div>`;
                            }
                            
                            update_scan_status(displayMessage, logType);
                        }
                        lastTimestamp = log.timestamp;
                    });
                }
            })
            .catch(error => {
                console.warn('Log polling error:', error);
            });
    };
    
    // Poll every 500ms during scan
    return setInterval(pollLogs, 500);
}

function stop_log_polling(intervalId) {
    if (intervalId) {
        clearInterval(intervalId);
    }
}

function disconnect_scanner_via_bridge() {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);  // Quick disconnect

    fetch(`${DESKTOP_BRIDGE_URL}/scanner/disconnect`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        signal: controller.signal
    })
        .then(response => {
            clearTimeout(timeoutId);
            return response.json();
        })
        .then(data => {
            console.log('Scanner disconnected:', data.success);
        })
        .catch(error => {
            clearTimeout(timeoutId);
            console.error('Error disconnecting scanner:', error);
        });
}

function save_fingerprint_to_erpnext(employee_id, finger_index, template_data, quality_score, callback) {
    // Handle optional quality_score parameter (backward compatibility)
    if (typeof quality_score === 'function') {
        callback = quality_score;
        quality_score = 0;
    }
    quality_score = quality_score || 0;
    
    console.log('save_fingerprint_to_erpnext called with:', {employee_id, finger_index, quality_score, template_data: template_data ? 'DATA_PRESENT' : 'NO_DATA'});
    
    frappe.call({
        method: 'customize_erpnext.api.utilities.save_fingerprint_data',
        args: {
            employee_id: employee_id,
            finger_index: finger_index,
            template_data: template_data,
            quality_score: quality_score
        },
        callback: function (r) {
            if (r.message && r.message.success) {
                callback(true, r.message.fingerprint_id);
            } else {
                callback(false, null);
            }
        },
        error: function () {
            callback(false, null);
        }
    });
}

// All status updates now use scan_status log area instead of alerts

// All complex functions removed - using standard Frappe dialog and alerts

function show_multi_employee_sync_dialog(listview) {
    // Get selected employees
    const selected_employees = listview.get_checked_items();

    if (selected_employees.length === 0) {
        frappe.msgprint({
            title: __('No Employees Selected'),
            message: __('Please select at least one employee from the list to sync fingerprints to attendance machines.'),
            indicator: 'orange'
        });
        return;
    }

    // Confirm action for multiple employees
    if (selected_employees.length > 1) {
        frappe.confirm(
            __('You have selected {0} employees. Do you want to sync fingerprints for all of them to attendance machines?', [selected_employees.length]),
            function() {
                // User confirmed, proceed with sync
                const employees = selected_employees.map(emp => ({
                    employee_id: emp.name,
                    employee_name: emp.employee_name || emp.name
                }));

                // Use shared sync dialog for multi-employee sync
                window.showSharedSyncDialog(employees, {
                    multi_employee: true,
                    source: 'employee_list'
                });
            }
        );
    } else {
        // Single employee selected
        const employee = selected_employees[0];
        const emp_data = {
            employee_id: employee.name,
            employee_name: employee.employee_name || employee.name
        };

        // Use shared sync dialog for single employee
        window.showSharedSyncDialog([emp_data], {
            source: 'employee_list'
        });
    }
}

function show_sync_fingerprint_from_attendance_machine_to_erp_dialog() {
    frappe.msgprint({
        title: __('Sync Fingerprint Data'),
        message: __('show_sync_fingerprint_from_attendance_machine_to_erp_dialog() will synchronize fingerprint data from attendance devices to ERP. Implementation will be completed in the next phase.'),
        indicator: 'blue'
    });
}

function show_sync_fingerprint_from_erp_to_attendance_machine_dialog() {
    frappe.msgprint({
        title: __('Legacy Function'),
        message: __('This function has been replaced by the new multi-employee sync. Please use "Sync Fingerprint From ERP To Attendance Machines" instead.'),
        indicator: 'blue'
    });
}