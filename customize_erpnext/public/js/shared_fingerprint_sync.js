// Shared fingerprint sync functionality with multi-threading optimization
// This module provides common functions for syncing fingerprints from ERP to attendance machines

window.FingerprintSyncManager = (function () {
    'use strict';

    // Configuration
    const CONFIG = {
        // Employees per batch request. Each machine gets one server call per
        // chunk; the server keeps ONE device connection per call (fast) while
        // chunking keeps individual HTTP requests well under gunicorn timeout.
        CHUNK_SIZE: 20
    };

    // Shared dialog instance
    let syncDialog = null;
    let currentSyncState = {
        isRunning: false,
        employees: [],
        totalMachines: 0,
        completedOperations: 0,
        failedOperations: [],   // [{employee_id, employee_name, machine, error}]
        realtimeBound: false,
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

        // Reset state from any previous run
        currentSyncState.completedOperations = 0;
        currentSyncState.failedOperations = [];
        currentSyncState.isRunning = false;

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
            : __('🔄 Sync Fingerprints to Machines - {0} {1}', [currentSyncState.employees[0].employee_id, currentSyncState.employees[0].employee_name]);

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
                        function () {
                            abortSyncProcess();
                        }
                    );
                } else if (currentSyncState.failedOperations.length > 0) {
                    retryFailedOperations();
                } else {
                    loadMachinesList();
                }
            }
        });

        // Add dialog close handler to prevent closing during sync
        syncDialog.onhide = function () {
            if (currentSyncState.isRunning) {
                frappe.confirm(
                    __('Sync is currently in progress. Closing this dialog will not stop the sync process, but you will lose the ability to monitor progress. Are you sure you want to close?'),
                    function () {
                        // User confirmed - allow close but warn about background process
                        frappe.show_alert({
                            message: __('Sync continues in background. Check console logs for progress.'),
                            indicator: 'orange'
                        });
                        currentSyncState.isRunning = false; // Allow future syncs
                        syncDialog.onhide = null; // Remove this handler
                        syncDialog.hide();
                    },
                    function () {
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
                            <small class="text-muted">Fingerprints will be synced to the machines selected below (all online machines are pre-selected)</small>
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
                            <small class="text-muted">Fingerprints will be synced to the machines selected below (all online machines are pre-selected)</small>
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
                    <button type="button" class="btn btn-xs btn-default ms-3" id="fp-sync-select-all" style="margin-left:12px;">☑ Select All</button>
                    <button type="button" class="btn btn-xs btn-default ms-1" id="fp-sync-unselect-all" style="margin-left:6px;">☐ Unselect All</button>
                </div>
                <div class="d-flex align-items-center">
                    <small class="badge bg-primary text-white me-1" id="fp-sync-selected-count"></small>
                    <small class="badge bg-success text-white me-1">🟢 ${online_machines}</small>
                    <small class="badge bg-secondary text-white me-1">🔴 ${offline_machines}</small>
                    <small class="text-muted ms-2">${new Date().toLocaleTimeString()}</small>
                </div>
            </div>
        `;

        html += `
            <div class="table-responsive">
                <table class="table table-sm table-hover mb-2">
                    <thead class="table-light">
                        <tr>
                            <th style="width: 5%; text-align:center"><i class="fa fa-check-square-o"></i></th>
                            <th style="width: 27%"><i class="fa fa-tag me-1"></i>Name</th>
                            <th style="width: 33%"><i class="fa fa-network-wired me-1"></i>Address</th>
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
            const isOnline = machine.connection_status === 'online';

            html += `
                <tr class="${rowClass}" style="border-left: 3px solid var(--bs-${statusColor});">
                    <td style="text-align:center; vertical-align:middle;">
                        <input type="checkbox" class="fp-sync-machine-cb" data-machine-name="${frappe.utils.escape_html(machine.device_name)}"
                               ${isOnline ? 'checked' : 'disabled'} style="width:16px;height:16px;cursor:${isOnline ? 'pointer' : 'not-allowed'};">
                    </td>
                    <td>
                        <strong>${machine.device_name}</strong>
                        ${machine.location ? `<br><small class="text-muted">${machine.location}</small>` : ''}
                    </td>
                    <td>
                        <span class="font-monospace">${machine.ip_address}:${machine.port}</span>
                    </td>
                    <td>
                        <span class="badge bg-${statusColor} text-white">${statusIcon} ${machine.connection_status.toUpperCase()}</span>
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
        currentSyncState.machines = machines;

        // Wire up machine selection (checkbox per machine + select/unselect all)
        machinesDiv.querySelectorAll('.fp-sync-machine-cb').forEach(cb =>
            cb.addEventListener('change', onMachineSelectionChange));
        const selAll = machinesDiv.querySelector('#fp-sync-select-all');
        const unselAll = machinesDiv.querySelector('#fp-sync-unselect-all');
        if (selAll) selAll.addEventListener('click', () => setAllMachineCheckboxes(true));
        if (unselAll) unselAll.addEventListener('click', () => setAllMachineCheckboxes(false));

        onMachineSelectionChange();
    }

    function setAllMachineCheckboxes(checked) {
        document.querySelectorAll('.fp-sync-machine-cb:not(:disabled)').forEach(cb => { cb.checked = checked; });
        onMachineSelectionChange();
    }

    function getSelectedMachineNames() {
        return [...document.querySelectorAll('.fp-sync-machine-cb:checked')].map(cb => cb.dataset.machineName);
    }

    function onMachineSelectionChange() {
        const selectedNames = new Set(getSelectedMachineNames());
        const selectedOnline = (currentSyncState.machines || [])
            .filter(m => m.connection_status === 'online' && selectedNames.has(m.device_name));

        currentSyncState.totalMachines = selectedOnline.length;

        const countBadge = document.getElementById('fp-sync-selected-count');
        if (countBadge) countBadge.textContent = `☑ ${selectedOnline.length} selected`;

        // Rebuild the per-machine progress grid for the selected machines only
        updateMachineProgressGrid(selectedOnline);

        // No machine selected -> block Start Sync (unless a sync is already running)
        if (syncDialog && !currentSyncState.isRunning) {
            if (selectedOnline.length === 0) {
                syncDialog.disable_primary_action();
            } else {
                syncDialog.enable_primary_action();
            }
        }
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
                                <span class="badge bg-secondary text-white" id="machine-status-${index}">Waiting</span>
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

    // Live per-employee progress pushed from the server during batch sync
    // (event published by utilities.sync_employees_to_machine_batch)
    function bindRealtimeProgress() {
        if (currentSyncState.realtimeBound) return;
        if (frappe.realtime && frappe.realtime.on) {
            frappe.realtime.on('fingerprint_machine_sync_progress', function (data) {
                if (!currentSyncState.isRunning || !data) return;
                if (data.success) {
                    updateSyncStatus(`  ✅ ${data.machine}: ${data.employee_name || data.employee} (${data.fingerprints_synced} fingerprints)`, 'success');
                } else {
                    updateSyncStatus(`  ⚠️ ${data.machine}: ${data.employee_name || data.employee} — ${data.error || 'failed'}`, 'warning');
                }
            });
            currentSyncState.realtimeBound = true;
        }
    }

    // Multi-threaded sync implementation
    async function startMultiThreadedSync() {
        if (currentSyncState.isRunning) return;

        currentSyncState.isRunning = true;
        currentSyncState.completedOperations = 0;
        currentSyncState.failedOperations = [];
        currentSyncState.abortController = new AbortController();
        bindRealtimeProgress();

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

            // Only sync to machines the user left checked in the machines list
            const selectedNames = new Set(getSelectedMachineNames());
            const onlineMachines = machinesResponse.machines.filter(
                m => m.connection_status === 'online' && selectedNames.has(m.device_name));

            if (onlineMachines.length === 0) {
                throw new Error('No machine selected for sync — tick at least one online machine in the list');
            }

            updateSyncStatus(`✅ Found ${onlineMachines.length} online machines`, 'success');
            updateProgressBar(0, `Starting sync to ${onlineMachines.length} machines...`);

            // Calculate total operations
            const totalOperations = currentSyncState.employees.length * onlineMachines.length;
            updateSyncStatus(`📊 Total operations: ${currentSyncState.employees.length} employees × ${onlineMachines.length} machines = ${totalOperations}`, 'info');
            updateSyncStatus(`⚡ Strategy: one device connection per batch of ${CONFIG.CHUNK_SIZE} employees, machines run in parallel`, 'info');

            // Start all machines in parallel - each machine processes all employees
            const machinePromises = onlineMachines.map((machine, machineIndex) =>
                syncEmployeesToMachineInChunks(machine, machineIndex, currentSyncState.employees, totalOperations)
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

    async function syncEmployeesToMachineInChunks(machine, machineIndex, employees, totalOperations) {
        // One server call per chunk; the server keeps a single device
        // connection per call and returns per-employee results.
        updateMachineStatus(machineIndex, 'warning', '🔄 Starting');
        updateSyncStatus(`\n🖥️  ${machine.device_name}: Syncing ${employees.length} employees (batches of ${CONFIG.CHUNK_SIZE})...`, 'info');

        let successCount = 0;
        let failCount = 0;
        let processed = 0;

        for (let start = 0; start < employees.length; start += CONFIG.CHUNK_SIZE) {
            // Check if sync was aborted
            if (currentSyncState.abortController && currentSyncState.abortController.signal.aborted) {
                throw new Error('Sync aborted by user');
            }

            const chunk = employees.slice(start, start + CONFIG.CHUNK_SIZE);
            const employeeById = {};
            chunk.forEach(e => { employeeById[e.employee_id] = e; });

            const result = await callFrappeMethod(
                'customize_erpnext.api.utilities.sync_employees_to_machine_batch',
                {
                    machine_name: machine.name,
                    employee_ids: JSON.stringify(chunk.map(e => e.employee_id))
                }
            );

            (result.results || []).forEach(r => {
                processed++;
                currentSyncState.completedOperations++;
                if (r.success) {
                    successCount++;
                } else {
                    failCount++;
                    const emp = employeeById[r.employee] || {};
                    currentSyncState.failedOperations.push({
                        employee_id: r.employee,
                        employee_name: r.employee_name || emp.employee_name || r.employee,
                        machine: machine.device_name,
                        machine_name: machine.name,
                        error: r.error || 'Unknown error'
                    });
                }
            });

            updateMachineStatus(machineIndex, 'warning', `🔄 ${processed}/${employees.length}`);
            const overallProgress = Math.round((currentSyncState.completedOperations / totalOperations) * 100);
            updateProgressBar(overallProgress, `${currentSyncState.completedOperations}/${totalOperations} operations completed`);
        }

        // Final status for this machine
        updateMachineStatus(machineIndex,
            failCount === 0 ? 'success' : 'warning',
            `${failCount === 0 ? '✅' : '⚠️'} ${successCount}/${employees.length}`);

        return {
            success: true,
            machine: machine.device_name,
            successCount: successCount,
            failCount: failCount,
            total: employees.length
        };
    }

    async function retryFailedOperations() {
        // Re-sync only the failed (employee, machine) pairs from the last run
        const failures = currentSyncState.failedOperations.slice();
        if (failures.length === 0 || currentSyncState.isRunning) return;

        currentSyncState.isRunning = true;
        currentSyncState.failedOperations = [];
        currentSyncState.abortController = new AbortController();
        bindRealtimeProgress();

        syncDialog.set_primary_action(__('Retrying...'), null);
        syncDialog.disable_primary_action();
        syncDialog.set_secondary_action_label(__('🛑 Abort Sync'));

        updateSyncStatus(`\n🔁 Retrying ${failures.length} failed operation(s)...`, 'info');

        // Group failures by machine
        const byMachine = {};
        failures.forEach(f => {
            if (!byMachine[f.machine_name]) byMachine[f.machine_name] = { machine: f.machine, employees: [] };
            byMachine[f.machine_name].employees.push(f);
        });

        try {
            await Promise.allSettled(Object.entries(byMachine).map(async ([machineName, group]) => {
                for (let start = 0; start < group.employees.length; start += CONFIG.CHUNK_SIZE) {
                    if (currentSyncState.abortController && currentSyncState.abortController.signal.aborted) return;
                    const chunk = group.employees.slice(start, start + CONFIG.CHUNK_SIZE);
                    const result = await callFrappeMethod(
                        'customize_erpnext.api.utilities.sync_employees_to_machine_batch',
                        {
                            machine_name: machineName,
                            employee_ids: JSON.stringify(chunk.map(e => e.employee_id))
                        }
                    );
                    (result.results || []).forEach(r => {
                        if (!r.success) {
                            currentSyncState.failedOperations.push({
                                employee_id: r.employee,
                                employee_name: r.employee_name || r.employee,
                                machine: group.machine,
                                machine_name: machineName,
                                error: r.error || 'Unknown error'
                            });
                        }
                    });
                }
            }));

            const stillFailed = currentSyncState.failedOperations.length;
            if (stillFailed === 0) {
                updateSyncStatus(`✅ Retry completed — all ${failures.length} operation(s) succeeded`, 'success');
                frappe.show_alert({ message: __('Retry successful!'), indicator: 'green' });
            } else {
                updateSyncStatus(`⚠️ Retry completed — ${failures.length - stillFailed} fixed, ${stillFailed} still failing:`, 'warning');
                currentSyncState.failedOperations.forEach(f =>
                    updateSyncStatus(`   • ${f.machine}: ${f.employee_name} — ${f.error}`, 'danger'));
            }
        } catch (error) {
            updateSyncStatus(`❌ Retry failed: ${error.message}`, 'danger');
        } finally {
            currentSyncState.isRunning = false;
            currentSyncState.abortController = null;
            resetSyncButton();
        }
    }

    function updateMachineStatus(machineIndex, type, status) {
        const statusBadge = document.getElementById(`machine-status-${machineIndex}`);
        const progressBar = document.getElementById(`machine-progress-${machineIndex}`);

        if (statusBadge) {
            statusBadge.className = `badge bg-${type} text-white`;
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
        const failed = currentSyncState.failedOperations.length;
        const succeeded = Math.max(currentSyncState.completedOperations - failed, 0);
        const successRate = totalOperations ? Math.round((succeeded / totalOperations) * 100) : 0;

        updateSyncStatus('\n📊 SYNC SUMMARY:', 'info');
        updateSyncStatus(`   👥 Employees processed: ${currentSyncState.employees.length}`, 'info');
        updateSyncStatus(`   🖥️ Machine operations: ${succeeded}/${totalOperations} succeeded`, 'info');
        updateSyncStatus(`   📈 Success rate: ${successRate}%`, 'info');

        // Per-employee failure list with reasons
        if (failed > 0) {
            updateSyncStatus(`\n❌ Failed operations (${failed}):`, 'danger');
            currentSyncState.failedOperations.slice(0, 30).forEach(f =>
                updateSyncStatus(`   • ${f.machine}: ${f.employee_name} — ${f.error}`, 'danger'));
            if (failed > 30) {
                updateSyncStatus(`   ... and ${failed - 30} more`, 'danger');
            }
            updateSyncStatus(`👉 Use the "🔁 Retry Failed" button to re-sync only the failed employees.`, 'warning');
        }

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

        // Secondary button: retry failed ops if any, otherwise refresh machines
        const failed = currentSyncState.failedOperations.length;
        syncDialog.set_secondary_action_label(
            failed > 0 ? __('🔁 Retry Failed ({0})', [failed]) : __('🔄 Refresh Machines'));
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
                type: 'POST',
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