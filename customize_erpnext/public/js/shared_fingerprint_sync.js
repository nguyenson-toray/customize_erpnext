// Shared fingerprint sync functionality with multi-threading optimization
// This module provides common functions for syncing fingerprints from ERP to attendance machines

window.FingerprintSyncManager = (function () {
    'use strict';

    // Configuration
    const CONFIG = {
        CONCURRENT_MACHINES: 10, // Not used in "per-machine" strategy, kept for compatibility
        MACHINE_TIMEOUT: 15000, // 15 seconds timeout per employee sync
        RETRY_ATTEMPTS: 2,
        RETRY_DELAY: 1000, // 1 second
        SYNC_STRATEGY: 'per-machine' // Each machine processes all employees sequentially, machines run in parallel
    };

    // Shared dialog instance
    let syncDialog = null;
    let currentSyncState = {
        isRunning: false,
        employees: [],
        totalMachines: 0,
        completedMachines: 0,
        syncResults: [],
        abortController: null // For canceling ongoing sync operations
    };

    // Main function to show sync dialog for single or multiple employees
    function showSyncDialog(employees, options = {}) {
        if (!Array.isArray(employees)) {
            employees = [employees];
        }

        // Validate employees
        const validEmployees = employees.filter(emp => {
            if (typeof emp === 'string') {
                return emp.trim().length > 0;
            }
            return emp && (emp.employee_id || emp.name) && emp.employee_name;
        });

        if (validEmployees.length === 0) {
            frappe.msgprint({
                title: __('No Employees Selected'),
                message: __('Please select at least one employee to sync fingerprints.'),
                indicator: 'orange'
            });
            return;
        }

        // Normalize employee data
        currentSyncState.employees = validEmployees.map(emp => {
            if (typeof emp === 'string') {
                return { employee_id: emp, employee_name: emp };
            }
            return {
                employee_id: emp.employee_id || emp.name,
                employee_name: emp.employee_name || emp.name || emp.employee_id
            };
        });

        createSyncDialog(options);
    }

    function createSyncDialog(options = {}) {
        const isMultiEmployee = currentSyncState.employees.length > 1;
        const title = isMultiEmployee
            ? __('🔄 Sync Fingerprints to Machines - {0} Employees', [currentSyncState.employees.length])
            : __('🔄 Sync Fingerprints to Machines - {0}', [currentSyncState.employees[0].employee_name]);

        syncDialog = new frappe.ui.Dialog({
            title: title,
            fields: [
                {
                    fieldname: 'employee_info',
                    fieldtype: 'HTML',
                    options: generateEmployeeInfoHTML()
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
                    fieldname: 'sync_progress',
                    fieldtype: 'HTML',
                    options: generateProgressHTML()
                },
                {
                    fieldname: 'sync_status',
                    fieldtype: 'HTML',
                    options: '<div id="sync-status" style="height: 300px; overflow-y: auto; padding: 15px; border-radius: 8px; background: #f8f9fa; border: 1px solid #dee2e6; font-family: monospace; font-size: 13px;"><div class="text-info">Ready to sync fingerprints to attendance machines...</div></div>'
                }
            ],
            primary_action_label: __('🚀 Start Sync'),
            primary_action: function () {
                startMultiThreadedSync();
            },
            secondary_action_label: __('🔄 Refresh Machines'),
            secondary_action: function () {
                if (currentSyncState.isRunning) {
                    // If sync is running, make secondary button an abort button
                    frappe.confirm(
                        __('Are you sure you want to abort the sync process? This will stop all ongoing operations.'),
                        function() {
                            abortSyncProcess();
                        }
                    );
                } else {
                    loadMachinesList();
                }
            }
        });

        // Add dialog close handler to prevent closing during sync
        syncDialog.onhide = function() {
            if (currentSyncState.isRunning) {
                frappe.confirm(
                    __('Sync is currently in progress. Closing this dialog will not stop the sync process, but you will lose the ability to monitor progress. Are you sure you want to close?'),
                    function() {
                        // User confirmed - allow close but warn about background process
                        frappe.show_alert({
                            message: __('Sync continues in background. Check console logs for progress.'),
                            indicator: 'orange'
                        });
                        currentSyncState.isRunning = false; // Allow future syncs
                        syncDialog.onhide = null; // Remove this handler
                        syncDialog.hide();
                    },
                    function() {
                        // User cancelled - keep dialog open
                        return false;
                    }
                );
                return false; // Prevent closing
            }
            return true; // Allow closing when not syncing
        };

        syncDialog.show();
        styleSyncDialog();

        // Load machines list after dialog is shown
        setTimeout(() => {
            loadMachinesList();
        }, 500);
    }

    function generateEmployeeInfoHTML() {
        const isMultiEmployee = currentSyncState.employees.length > 1;

        if (isMultiEmployee) {
            const employeeList = currentSyncState.employees
                .slice(0, 5) // Show first 5
                .map(emp => `<li><strong>${emp.employee_name}</strong> (${emp.employee_id})</li>`)
                .join('');

            const moreText = currentSyncState.employees.length > 5
                ? `<li class="text-muted">... and ${currentSyncState.employees.length - 5} more employees</li>`
                : '';

            return `
                <div class="alert alert-info" style="margin-bottom: 15px;">
                    <div class="d-flex align-items-start">
                        <i class="fa fa-users" style="font-size: 20px; margin-right: 10px; margin-top: 2px;"></i>
                        <div>
                            <strong>Selected Employees (${currentSyncState.employees.length}):</strong>
                            <ul style="margin: 8px 0 5px 0; padding-left: 20px;">
                                ${employeeList}
                                ${moreText}
                            </ul>
                            <small class="text-muted">Fingerprints will be synced to all enabled attendance machines simultaneously</small>
                        </div>
                    </div>
                </div>
            `;
        } else {
            const emp = currentSyncState.employees[0];
            return `
                <div class="alert alert-info" style="margin-bottom: 15px;">
                    <div class="d-flex align-items-center">
                        <i class="fa fa-user" style="font-size: 20px; margin-right: 10px;"></i>
                        <div>
                            <strong>Employee:</strong> ${emp.employee_name} (${emp.employee_id})<br>
                            <small class="text-muted">Fingerprints will be synced to all enabled attendance machines</small>
                        </div>
                    </div>
                </div>
            `;
        }
    }

    function generateProgressHTML() {
        return `
            <div id="sync-progress-container" style="margin-bottom: 15px;">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <strong>Overall Progress</strong>
                    <span id="sync-progress-text">Ready to start</span>
                </div>
                <div class="progress mb-3" style="height: 25px;">
                    <div id="sync-progress-bar" class="progress-bar progress-bar-striped"
                         role="progressbar" style="width: 0%;">0%</div>
                </div>
                <div class="row" id="machine-progress-grid"></div>
            </div>
        `;
    }

    function styleSyncDialog() {
        syncDialog.$wrapper.find('.modal-dialog').addClass('modal-xl');
        syncDialog.$wrapper.find('.modal-content').css({
            'border-radius': '12px',
            'box-shadow': '0 10px 30px rgba(0,0,0,0.2)'
        });
        syncDialog.$wrapper.find('.modal-header').css({
            'background': 'linear-gradient(135deg, #28a745 0%, #20c997 100%)',
            'color': 'white',
            'border-bottom': 'none',
            'border-radius': '12px 12px 0 0'
        });
    }

    function loadMachinesList() {
        const machinesDiv = document.getElementById('machines-list');
        if (!machinesDiv) return;

        machinesDiv.innerHTML = '<div class="text-center text-muted"><i class="fa fa-spinner fa-spin"></i> Checking attendance machines...</div>';

        frappe.call({
            method: 'customize_erpnext.api.utilities.get_enabled_attendance_machines',
            callback: function (r) {
                if (r.message && r.message.success) {
                    displayMachinesList(r.message);
                } else {
                    machinesDiv.innerHTML = `<div class="alert alert-warning"><i class="fa fa-exclamation-triangle"></i> ${r.message.message || 'Failed to load machines'}</div>`;
                }
            },
            error: function (r) {
                machinesDiv.innerHTML = `<div class="alert alert-danger"><i class="fa fa-times"></i> Error loading machines: ${r.exc || 'Unknown error'}</div>`;
            }
        });
    }

    function displayMachinesList(data) {
        const machinesDiv = document.getElementById('machines-list');
        if (!machinesDiv || !data.machines) return;

        const { machines, total_machines, online_machines, offline_machines } = data;
        currentSyncState.totalMachines = online_machines;

        if (machines.length === 0) {
            machinesDiv.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fa fa-exclamation-triangle me-2"></i>
                    <strong>No master machines found.</strong> Please enable at least one attendance machine.
                </div>
            `;
            return;
        }

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

        if (offline_machines > 0) {
            html += `<div class="alert alert-warning py-2 mb-2">
                <i class="fa fa-exclamation-triangle me-1"></i>
                <small><strong>${offline_machines}</strong> machine(s) offline. Sync will work with <strong>${online_machines}</strong> online machines.</small>
            </div>`;
        } else {
            html += `<div class="alert alert-success py-2 mb-2">
                <i class="fa fa-check-circle me-1"></i>
                <small>All <strong>${online_machines}</strong> machines are online and ready for sync.</small>
            </div>`;
        }

        machinesDiv.innerHTML = html;
        updateMachineProgressGrid(machines.filter(m => m.connection_status === 'online'));
    }

    function updateMachineProgressGrid(onlineMachines) {
        const gridDiv = document.getElementById('machine-progress-grid');
        if (!gridDiv || !onlineMachines) return;

        let html = '';
        onlineMachines.forEach((machine, index) => {
            html += `
                <div class="col-md-4 col-sm-6 mb-2">
                    <div class="card border-0 shadow-sm" id="machine-card-${index}">
                        <div class="card-body p-2">
                            <div class="d-flex justify-content-between align-items-center">
                                <small><strong>${machine.device_name}</strong></small>
                                <span class="badge badge-secondary" id="machine-status-${index}">Waiting</span>
                            </div>
                            <div class="progress mt-1" style="height: 4px;">
                                <div class="progress-bar" id="machine-progress-${index}"
                                     role="progressbar" style="width: 0%;"></div>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });
        gridDiv.innerHTML = html;
    }

    // Multi-threaded sync implementation
    async function startMultiThreadedSync() {
        if (currentSyncState.isRunning) return;

        currentSyncState.isRunning = true;
        currentSyncState.completedMachines = 0;
        currentSyncState.syncResults = [];
        currentSyncState.abortController = new AbortController();

        // Disable sync button and update secondary button to show abort
        syncDialog.set_primary_action(__('Syncing...'), null);
        syncDialog.disable_primary_action();

        // Update secondary button label to show abort option
        syncDialog.set_secondary_action_label(__('🛑 Abort Sync'));

        updateSyncStatus('🔄 Starting multi-threaded sync process...', 'info');
        updateSyncStatus(`📋 Employees: ${currentSyncState.employees.length}`, 'info');
        updateSyncStatus(`🖥️ Target machines: ${currentSyncState.totalMachines}`, 'info');
        updateSyncStatus('🔍 Checking employee data and machines...', 'info');

        try {
            // Get machines list first
            const machinesResponse = await callFrappeMethod('customize_erpnext.api.utilities.get_enabled_attendance_machines');

            if (!machinesResponse.success || !machinesResponse.machines) {
                throw new Error(machinesResponse.message || 'Failed to get machines list');
            }

            const onlineMachines = machinesResponse.machines.filter(m => m.connection_status === 'online');

            if (onlineMachines.length === 0) {
                throw new Error('No online machines available for sync');
            }

            updateSyncStatus(`✅ Found ${onlineMachines.length} online machines`, 'success');
            updateProgressBar(0, `Starting sync to ${onlineMachines.length} machines...`);

            // Calculate total operations
            const totalOperations = currentSyncState.employees.length * onlineMachines.length;
            updateSyncStatus(`📊 Total operations: ${currentSyncState.employees.length} employees × ${onlineMachines.length} machines = ${totalOperations}`, 'info');
            updateSyncStatus(`⚡ Strategy: Each machine processes all employees sequentially, machines run in parallel`, 'info');

            // Start all machines in parallel - each machine processes all employees
            const machinePromises = onlineMachines.map((machine, machineIndex) =>
                syncAllEmployeesToSingleMachine(machine, machineIndex, currentSyncState.employees, totalOperations)
            );

            // Wait for all machines to complete
            const machineResults = await Promise.allSettled(machinePromises);

            // Process results
            machineResults.forEach((result, machineIndex) => {
                const machine = onlineMachines[machineIndex];

                if (result.status === 'fulfilled') {
                    updateSyncStatus(`\n✅ ${machine.device_name}: Completed all ${currentSyncState.employees.length} employees`, 'success');
                    updateMachineStatus(machineIndex, 'success', '✅ Complete');
                } else {
                    updateSyncStatus(`\n❌ ${machine.device_name}: Failed - ${result.reason.message}`, 'danger');
                    updateMachineStatus(machineIndex, 'danger', '❌ Failed');
                }
            });

            // Show final results
            showSyncSummary();

        } catch (error) {
            updateSyncStatus(`❌ Sync failed: ${error.message}`, 'danger');
            frappe.show_alert({
                message: __('Sync failed: ' + error.message),
                indicator: 'red'
            });
        } finally {
            currentSyncState.isRunning = false;
            currentSyncState.abortController = null;
            resetSyncButton();
            setTimeout(() => {
                updateSyncStatus('🔄 Refreshing machines status...', 'info');
                loadMachinesList();
            }, 2000);
        }
    }

    async function syncAllEmployeesToSingleMachine(machine, machineIndex, employees, totalOperations) {
        // This machine will process all employees sequentially
        updateMachineStatus(machineIndex, 'warning', '🔄 Starting');
        updateSyncStatus(`\n🖥️  ${machine.device_name}: Starting to process ${employees.length} employees...`, 'info');

        let successCount = 0;
        let failCount = 0;

        // Process each employee sequentially for this machine
        for (let empIndex = 0; empIndex < employees.length; empIndex++) {
            // Check if sync was aborted
            if (currentSyncState.abortController && currentSyncState.abortController.signal.aborted) {
                throw new Error('Sync aborted by user');
            }

            const employee = employees[empIndex];

            try {
                updateMachineStatus(machineIndex, 'warning', `🔄 ${empIndex + 1}/${employees.length}`);

                // Call backend API to sync one employee to this machine
                const result = await callFrappeMethod(
                    'customize_erpnext.api.utilities.sync_employee_to_single_machine',
                    {
                        employee_id: employee.employee_id,
                        machine_name: machine.name
                    }
                );

                if (result.success) {
                    successCount++;
                    currentSyncState.completedMachines++;
                    updateSyncStatus(`  ✅ ${machine.device_name}: ${employee.employee_name} (${empIndex + 1}/${employees.length})`, 'success');

                    // Update overall progress
                    const overallProgress = Math.round((currentSyncState.completedMachines / totalOperations) * 100);
                    updateProgressBar(overallProgress, `${currentSyncState.completedMachines}/${totalOperations} operations completed`);
                } else {
                    failCount++;
                    updateSyncStatus(`  ⚠️ ${machine.device_name}: ${employee.employee_name} - ${result.message}`, 'warning');
                }
            } catch (error) {
                failCount++;
                updateSyncStatus(`  ❌ ${machine.device_name}: ${employee.employee_name} - ${error.message}`, 'danger');
            }
        }

        // Final status for this machine
        updateMachineStatus(machineIndex, 'success', `✅ ${successCount}/${employees.length}`);

        return {
            success: true,
            machine: machine.device_name,
            successCount: successCount,
            failCount: failCount,
            total: employees.length
        };
    }

    function updateMachineStatus(machineIndex, type, status) {
        const statusBadge = document.getElementById(`machine-status-${machineIndex}`);
        const progressBar = document.getElementById(`machine-progress-${machineIndex}`);

        if (statusBadge) {
            statusBadge.className = `badge badge-${type}`;
            statusBadge.textContent = status;
        }

        if (progressBar) {
            const width = type === 'success' || type === 'danger' ? '100%' : '50%';
            progressBar.style.width = width;
            progressBar.className = `progress-bar${type === 'warning' ? ' progress-bar-striped progress-bar-animated' : ''}`;
        }
    }

    function updateProgressBar(percentage, text) {
        const progressBar = document.getElementById('sync-progress-bar');
        const progressText = document.getElementById('sync-progress-text');

        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.textContent = `${percentage}%`;
        }

        if (progressText && text) {
            progressText.textContent = text;
        }
    }

    function updateSyncStatus(message, type = 'info') {
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

            statusDiv.scrollTo({
                top: statusDiv.scrollHeight,
                behavior: 'smooth'
            });
        }
    }

    function showSyncSummary() {
        const totalOperations = currentSyncState.employees.length * currentSyncState.totalMachines;
        const successRate = Math.round((currentSyncState.completedMachines / totalOperations) * 100);

        updateSyncStatus('\n📊 SYNC SUMMARY:', 'info');
        updateSyncStatus(`   👥 Employees processed: ${currentSyncState.employees.length}`, 'info');
        updateSyncStatus(`   🖥️ Machine operations: ${currentSyncState.completedMachines}/${totalOperations}`, 'info');
        updateSyncStatus(`   📈 Success rate: ${successRate}%`, 'info');

        updateProgressBar(100, `Completed: ${successRate}% success rate`);

        if (successRate === 100) {
            frappe.show_alert({
                message: __('All fingerprints synced successfully!'),
                indicator: 'green'
            });
        } else if (successRate > 0) {
            frappe.show_alert({
                message: __('Sync partially completed. Check details in dialog.'),
                indicator: 'orange'
            });
        } else {
            frappe.show_alert({
                message: __('Sync failed for all operations.'),
                indicator: 'red'
            });
        }
    }

    function resetSyncButton() {
        syncDialog.set_primary_action(__('🚀 Start Sync'), function () {
            const statusDiv = document.getElementById('sync-status');
            if (statusDiv) {
                statusDiv.innerHTML = '<div class="text-info">Ready to sync fingerprints to attendance machines...</div>';
            }
            startMultiThreadedSync();
        });
        syncDialog.enable_primary_action();

        // Reset secondary button back to refresh
        syncDialog.set_secondary_action_label(__('🔄 Refresh Machines'));
    }

    function abortSyncProcess() {
        if (currentSyncState.abortController) {
            currentSyncState.abortController.abort();
            updateSyncStatus('🛑 Sync process aborted by user', 'warning');
        }

        currentSyncState.isRunning = false;
        currentSyncState.abortController = null;

        frappe.show_alert({
            message: __('Sync process has been aborted'),
            indicator: 'orange'
        });

        resetSyncButton();
    }

    // Helper function to call Frappe methods as promises
    function callFrappeMethod(method, args = {}) {
        return new Promise((resolve, reject) => {
            // Check if operation was aborted before making the call
            if (currentSyncState.abortController && currentSyncState.abortController.signal.aborted) {
                reject(new Error('Operation aborted'));
                return;
            }

            const call = frappe.call({
                method: method,
                args: args,
                callback: function (r) {
                    if (currentSyncState.abortController && currentSyncState.abortController.signal.aborted) {
                        reject(new Error('Operation aborted'));
                        return;
                    }

                    if (r.message) {
                        resolve(r.message);
                    } else {
                        reject(new Error('No response from server'));
                    }
                },
                error: function (r) {
                    if (currentSyncState.abortController && currentSyncState.abortController.signal.aborted) {
                        reject(new Error('Operation aborted'));
                        return;
                    }
                    reject(new Error(r.exc || 'Server error'));
                }
            });

            // Listen for abort signal
            if (currentSyncState.abortController) {
                currentSyncState.abortController.signal.addEventListener('abort', () => {
                    // Try to abort the frappe call if possible
                    if (call && call.abort) {
                        call.abort();
                    }
                    reject(new Error('Operation aborted'));
                });
            }
        });
    }

    // Public API
    return {
        showSyncDialog: showSyncDialog,
        CONFIG: CONFIG // Allow configuration changes
    };
})();

// Make it globally available
window.showSharedSyncDialog = window.FingerprintSyncManager.showSyncDialog;