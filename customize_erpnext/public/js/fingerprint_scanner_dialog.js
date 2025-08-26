/**
 * Fingerprint Scanner Dialog - Shared Module
 * Can be used from Employee Form and Employee List
 */

window.FingerprintScannerDialog = {

    // Desktop Bridge API Configuration
    DESKTOP_BRIDGE_URL: 'http://127.0.0.1:8080/api',

    // Global variables for tracking
    scan_dialog: null,
    scan_count: 0,

    /**
     * Show fingerprint scanner dialog for Employee Form (fixed employee)
     * @param {string} employee_id - Required employee ID (cannot be changed)
     * @param {string} employee_name - Employee name for display
     */
    showForEmployee: function (employee_id, employee_name = null) {
        let d = new frappe.ui.Dialog({
            title: __('🔍 Fingerprint Scanner - {0}', [employee_name || employee_id]),
            fields: [
                {
                    fieldname: 'employee_info',
                    fieldtype: 'HTML',
                    options: `<div class="alert alert-info" style="margin-bottom: 15px;">
                        <div class="d-flex align-items-center">
                            <i class="fa fa-user" style="font-size: 20px; margin-right: 10px;"></i>
                            <div>
                                <strong>Employee:</strong> ${employee_name || employee_id}<br>
                                <small class="text-muted">Scanning fingerprints for this employee only</small>
                            </div>
                        </div>
                    </div>`
                },
                {
                    fieldname: 'finger_selection',
                    fieldtype: 'Select',
                    label: __('Select Finger'),
                    options: [
                        '',
                        __('Left Little'),
                        __('Left Ring'),
                        __('Left Middle'),
                        __('Left Index'),
                        __('Left Thumb'),
                        __('Right Thumb'),
                        __('Right Index'),
                        __('Right Middle'),
                        __('Right Ring'),
                        __('Right Little')
                    ],
                    reqd: 1,
                    description: __('Choose which finger to scan'),
                    change: function () {
                        const finger_selection_name = this.get_value();

                        if (finger_selection_name) {
                            const finger_map = {
                                'Left Little': 0, 'Left Ring': 1, 'Left Middle': 2, 'Left Index': 3, 'Left Thumb': 4,
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
                if (!values.finger_selection) {
                    frappe.msgprint({
                        title: __('⚠️ Missing Information'),
                        message: __('Please select a Finger before scanning.'),
                        indicator: 'orange'
                    });
                    return;
                }
                // Create values object with fixed employee
                const scanValues = {
                    employee: employee_id,
                    finger_selection: values.finger_selection
                };
                FingerprintScannerDialog.startFingerprintCapture(scanValues, d);
            },
            secondary_action_label: __('🔄 Reset'),
            secondary_action() {
                d.set_value('finger_selection', '');
                FingerprintScannerDialog.updateScanStatus(__('🔄 Ready for new scan'), 'info');
                FingerprintScannerDialog.updateFingerStatusDisplay([]);
            }
        });

        d.show();

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
        FingerprintScannerDialog.scan_dialog = d;
        FingerprintScannerDialog.scan_count = 0;

        // Store the fixed employee ID in the dialog for use in reset function
        d.employee_id = employee_id;

        // Load fingerprint status for the fixed employee after DOM is ready
        setTimeout(() => {
            // Initialize finger status display first
            FingerprintScannerDialog.updateFingerStatusDisplay([]);

            // Then load actual data
            frappe.call({
                method: 'customize_erpnext.api.utilities.get_employee_fingerprints_status',
                args: { employee_id: employee_id },
                callback: function (r) {
                    if (r.message && r.message.success) {
                        FingerprintScannerDialog.updateFingerStatusDisplay(r.message.existing_fingers);
                    }
                }
            });
        }, 300);
    },

    updateFingerStatusDisplay: function (existing_fingers) {
        console.log('updateFingerStatusDisplay called with:', existing_fingers);
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
                0: "Left Little", 1: "Left Ring", 2: "Left Middle", 3: "Left Index", 5: "Left Thumb",
                5: "Right Thumb", 6: "Right Index", 7: "Right Middle", 8: "Right Ring", 9: "Right Little"
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
                    FingerprintScannerDialog.updateFingerStatusDisplay(existing_fingers);
                }
            }, 500);
        }
    },

    startFingerprintCapture: function (values, dialog) {
        // Get finger index from selection
        const finger_map = {
            'Left Little': 0, 'Left Ring': 1, 'Left Middle': 2, 'Left Index': 3, 'Left Thumb': 4,
            'Right Thumb': 5, 'Right Index': 6, 'Right Middle': 7, 'Right Ring': 8, 'Right Little': 9
        };

        const finger_index = finger_map[values.finger_selection];

        // Initialize scan attempt counter if not exists
        if (!FingerprintScannerDialog.scan_attempts) {
            FingerprintScannerDialog.scan_attempts = {};
        }

        // Reset attempt counter for this finger
        const attempt_key = `${values.employee}_${finger_index}`;
        FingerprintScannerDialog.scan_attempts[attempt_key] = 0;

        // Keep dialog open but disable scan button during process
        dialog.set_primary_action(__('Scanning...'), null);
        dialog.disable_primary_action();

        // Update status in dialog with scan attempt indicator
        FingerprintScannerDialog.updateScanStatus(__('🔍 Starting fingerprint scan process...'), 'info');
        FingerprintScannerDialog.updateScanStatus(__('📡 Checking Desktop Bridge connection...'), 'info');
        FingerprintScannerDialog.updateScanStatus(__('📋 Process: LẦN 1 → LẦN 2 → LẦN 3 → Merge → Complete'), 'info');

        // Step 1: Check desktop bridge availability
        FingerprintScannerDialog.checkDesktopBridgeStatus(function (bridgeAvailable) {
            if (!bridgeAvailable) {
                FingerprintScannerDialog.updateScanStatus(__('❌ Desktop Bridge connection failed! Please restart the application.'), 'danger');
                FingerprintScannerDialog.resetScanButton(dialog);
                return;
            }

            FingerprintScannerDialog.updateScanStatus(__('✅ Desktop Bridge connected. Initializing scanner...'), 'success');

            // Step 2: Initialize scanner via desktop bridge
            FingerprintScannerDialog.initializeScannerViaBridge(function (success, message) {
                if (success) {
                    FingerprintScannerDialog.updateScanStatus(__('🔍 Scanner ready! Starting capture...'), 'success');

                    // Step 3: Capture fingerprint
                    setTimeout(() => {
                        FingerprintScannerDialog.captureFingerprintData(values.employee, finger_index, values.finger_selection, dialog);
                    }, 500);

                } else {
                    FingerprintScannerDialog.updateScanStatus(__('❌ Scanner initialization failed: ' + message), 'danger');
                    FingerprintScannerDialog.resetScanButton(dialog);
                }
            });
        });
    },

    captureFingerprintData: function (employee_id, finger_index, finger_name, dialog) {
        FingerprintScannerDialog.updateScanStatus(__('🔄 Starting fingerprint enrollment process...'), 'info');

        // Use direct enrollment via bridge (single API call with real-time updates)
        FingerprintScannerDialog.captureFingerprintViaBridge(employee_id, finger_index, function (success, data, message) {
            if (success) {
                const final_template_data = data.template_data;
                const final_template_size = data.template_size;
                const quality_score = data.quality_score || data.quality || 0; // Try different property names

                console.log('Debug: Fingerprint data received:', { template_size: final_template_size, quality_score, data_keys: Object.keys(data) });

                FingerprintScannerDialog.updateScanStatus(`✅ Fingerprint enrollment completed! (${final_template_size} bytes, Quality: ${quality_score})`, 'success');

                // Save to ERPNext database  
                console.log('Debug: employee_id =', employee_id, 'finger_index =', finger_index);
                FingerprintScannerDialog.saveFingerprintToERPNext(employee_id, finger_index, final_template_data, quality_score, function (saveSuccess, fingerprintId) {
                    if (saveSuccess) {
                        FingerprintScannerDialog.updateScanStatus(__('💾 Fingerprint saved to database successfully'), 'success');
                        FingerprintScannerDialog.addScanToHistory(employee_id, finger_name, final_template_size, 'success');

                        // Refresh finger status display
                        frappe.call({
                            method: 'customize_erpnext.api.utilities.get_employee_fingerprints_status',
                            args: { employee_id: employee_id },
                            callback: function (r) {
                                if (r.message && r.message.success) {
                                    FingerprintScannerDialog.updateFingerStatusDisplay(r.message.existing_fingers);
                                }
                            }
                        });

                        setTimeout(() => {
                            dialog.set_value('finger_selection', '');
                            FingerprintScannerDialog.updateScanStatus(__('🟢 Ready for next scan'), 'info');
                            FingerprintScannerDialog.resetScanButton(dialog);
                        }, 1500);  // Reduced delay
                    } else {
                        FingerprintScannerDialog.updateScanStatus(__('❌ Failed to save to database'), 'danger');
                        FingerprintScannerDialog.addScanToHistory(employee_id, finger_name, 0, 'failed');
                        FingerprintScannerDialog.resetScanButton(dialog);
                    }
                    FingerprintScannerDialog.disconnectScannerViaBridge();
                });
            } else {
                FingerprintScannerDialog.updateScanStatus(`❌ Enrollment failed: ${message}`, 'danger');
                FingerprintScannerDialog.addScanToHistory(employee_id, finger_name, 0, 'failed');
                FingerprintScannerDialog.resetScanButton(dialog);
                FingerprintScannerDialog.disconnectScannerViaBridge();
            }
        });
    },

    updateScanStatus: function (message, type = 'info') {
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
    },

    resetScanButton: function (dialog) {
        dialog.set_primary_action(__('🔍 Start Scan'), function (values) {
            if (!values.finger_selection) {
                frappe.msgprint({
                    title: __('⚠️ Missing Information'),
                    message: __('Please select a Finger before scanning.'),
                    indicator: 'orange'
                });
                return;
            }

            // Create values object with fixed employee from dialog
            const scanValues = {
                employee: dialog.employee_id,
                finger_selection: values.finger_selection
            };

            // Reset attempt counter when starting fresh scan
            if (FingerprintScannerDialog.scan_attempts && scanValues.employee && scanValues.finger_selection) {
                const finger_map = {
                    'Left Little': 0, 'Left Ring': 1, 'Left Middle': 2, 'Left Index': 3, 'Left Thumb': 4,
                    'Right Thumb': 5, 'Right Index': 6, 'Right Middle': 7, 'Right Ring': 8, 'Right Little': 9
                };
                const finger_index = finger_map[scanValues.finger_selection];
                const attempt_key = `${scanValues.employee}_${finger_index}`;
                FingerprintScannerDialog.scan_attempts[attempt_key] = 0;
            }
            FingerprintScannerDialog.startFingerprintCapture(scanValues, dialog);
        });
        dialog.enable_primary_action();
    },

    addScanToHistory: function (employee_id, finger_name, template_size, status) {
        FingerprintScannerDialog.scan_count++;
        const scanList = document.getElementById('scan-list');
        if (scanList) {
            // Clear "No scans yet" message
            if (FingerprintScannerDialog.scan_count === 1) {
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
                            <span class="badge badge-primary me-2">#${FingerprintScannerDialog.scan_count}</span>
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
    },

    // Desktop Bridge API Functions
    checkDesktopBridgeStatus: function (callback) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3000);

        fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/test`, {
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

                // Show specific error message to user
                frappe.msgprint({
                    title: __('🚫 Desktop Bridge Connection Failed'),
                    message: __(`
                        <div style="margin: 15px 0;">
                            <h5>❌ Cannot connect to Fingerprint Scanner Bridge</h5>
                            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0;">
                                <p><strong>Required Action:</strong></p>
                                <ol>
                                    <li>🔴 Close the "Fingerprint Scanner" desktop application</li>
                                    <li>⏳ Wait 5 seconds</li>
                                    <li>🟢 Restart the "Fingerprint Scanner" desktop application</li>
                                    <li>🔄 Try scanning again</li>
                                </ol>
                            </div>
                            <div style="background: #e7f3ff; padding: 10px; border-radius: 5px; font-size: 12px;">
                                💡 <strong>Technical Details:</strong><br>
                                - Bridge URL: ${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}<br>
                                - Error: Connection timeout or application not running
                            </div>
                        </div>
                    `),
                    indicator: 'red',
                    primary_action: {
                        label: __('Retry Connection'),
                        action: function () {
                            // Retry after user clicks
                            FingerprintScannerDialog.checkDesktopBridgeStatus(callback);
                        }
                    }
                });

                callback(false);
            });
    },

    initializeScannerViaBridge: function (callback) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 8000);

        fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/scanner/initialize`, {
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
    },

    captureFingerprintViaBridge: function (employee_id, finger_index, callback) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);

        // Start polling logs for real-time updates BEFORE making the capture request
        const pollInterval = FingerprintScannerDialog.startLogPolling();

        // Small delay to ensure polling is active before bridge starts logging
        setTimeout(() => {
            fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/fingerprint/capture`, {
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
                    FingerprintScannerDialog.stopLogPolling(pollInterval);
                    callback(data.success, data, data.message);
                })
                .catch(error => {
                    clearTimeout(timeoutId);
                    console.error('Error capturing fingerprint:', error);
                    // Stop polling on error
                    FingerprintScannerDialog.stopLogPolling(pollInterval);
                    callback(false, null, 'Fingerprint capture timeout or network error');
                });
        }, 300);  // 300ms delay to ensure log polling is active
    },

    startLogPolling: function () {
        // Start polling from 2 seconds ago to catch any logs that might have been generated
        let startTime = new Date();
        startTime.setSeconds(startTime.getSeconds() - 2);
        let lastTimestamp = startTime.toTimeString().substring(0, 8);

        const pollLogs = () => {
            fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/logs/since?since=${lastTimestamp}`)
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

                                FingerprintScannerDialog.updateScanStatus(displayMessage, logType);
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
    },

    stopLogPolling: function (intervalId) {
        if (intervalId) {
            clearInterval(intervalId);
        }
    },

    disconnectScannerViaBridge: function () {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/scanner/disconnect`, {
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
    },

    saveFingerprintToERPNext: function (employee_id, finger_index, template_data, quality_score, callback) {
        // Handle optional quality_score parameter (backward compatibility)
        if (typeof quality_score === 'function') {
            callback = quality_score;
            quality_score = 0;
        }
        quality_score = quality_score || 0;

        console.log('saveFingerprintToERPNext called with:', { employee_id, finger_index, quality_score, template_data: template_data ? 'DATA_PRESENT' : 'NO_DATA' });

        if (!employee_id) {
            console.error('employee_id is missing!');
            frappe.msgprint({
                title: __('Error'),
                message: __('Employee ID is missing. Please refresh the page and try again.'),
                indicator: 'red'
            });
            if (callback) callback(false, null);
            return;
        }

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
            error: function (r) {
                callback(false, null);
            }
        });
    }
};

