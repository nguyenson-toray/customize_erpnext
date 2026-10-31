// Biometric Sync — Page desk, mở trong desk có sidebar Devices and Security.
// Chuyển từ trang www /biometric_sync (đã xoá 19/10/2026) bằng scripts/convert_biometric_page.py;
// từ đó FILE NÀY là nguồn chính — sửa trực tiếp ở đây. Tài liệu: biometric_sync.md cùng thư mục.
// Plan: .claude/plans/biometric_sync_desk_page.md. Chạy thử: scripts/smoke_biometric_page.js.
//
// Toàn bộ code cũ chạy trong bsync.setup(root) (closure, không còn 70 hàm global); handler inline
// gọi qua namespace `bsync.*`. CSS giới hạn trong .bsync (biometric_sync.css).

frappe.provide("bsync");

// HTML nằm ngay trong file JS (template literal): file .html của Page bị frappe nhúng thành chuỗi
// bọc nháy đơn mà KHÔNG escape nháy đơn bên trong -> onclick="bsync.switchTab('x')" làm gãy cả script.
const BSYNC_HTML = `<div class="bsync">


    <div class="main-wrap">

        <!-- Tab Nav -->
        <div class="tab-nav-wrap">
            <button class="tab-btn active" data-tab="tab-logs" onclick="bsync.switchTab('tab-logs')">
                <span class="tab-icon">📋</span><span class="tab-label">Logs</span>
            </button>
            <button class="tab-btn" data-tab="tab-fingerprint" onclick="bsync.switchTab('tab-fingerprint')">
                <span class="tab-icon">🔄</span><span class="tab-label">Sync Device → Device &amp; ERP</span>
            </button>
            <button class="tab-btn" data-tab="tab-fp41" onclick="bsync.switchTab('tab-fp41')">
                <span class="tab-icon">⬆</span><span class="tab-label">Sync ERP → Machines</span>
            </button>
            <button class="tab-btn" data-tab="tab-del43" onclick="bsync.switchTab('tab-del43')">
                <span class="tab-icon">🗑</span><span class="tab-label">Remove Left Staff</span>
            </button>
            <button class="tab-btn" data-tab="tab-machines" onclick="bsync.switchTab('tab-machines')">
                <span class="tab-icon">🖥</span><span class="tab-label">Machine Management</span>
            </button>
            <button class="tab-btn" data-tab="tab-resync" onclick="bsync.switchTab('tab-resync')">
                <span class="tab-icon">🔧</span><span class="tab-label">Manual Re-sync</span>
            </button>
        </div>

        <!-- ════════════════════════════════════════════════════════
             TAB 1: SYNC LOGS
        ════════════════════════════════════════════════════════ -->
        <div id="tab-logs" class="tab-panel active">
            <div class="card">
                <div class="card-title" style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                    <span>Automatic Log Pull</span>
                    <button class="btn btn-sm btn-secondary" onclick="bsync.loadSyncStatus()">↻ Refresh</button>
                </div>
                <div id="syncStatusSummary" class="stats">Loading...</div>
                <div id="syncStatusAlert"></div>
                <div style="overflow-x:auto;margin-top:10px;">
                    <table>
                        <thead><tr>
                            <th>Machine</th><th>Latest checkin in ERP</th><th>Logs on device</th>
                            <th title="Punches written to ERP in the last cycle">Inserted</th><th>Read time</th><th>Status</th>
                        </tr></thead>
                        <tbody id="syncStatusRows"></tbody>
                    </table>
                </div>
                <div id="mongoStatus" class="stats" style="margin-top:10px;"></div>
            </div>

            <div class="card">
                <div class="card-title" style="cursor:pointer;" onclick="bsync.toggleRawLog()">
                    <span id="rawLogArrow">▸</span> Raw log
                </div>
                <div id="rawLogBody" style="display:none;">
                    <div class="log-controls">
                        <div class="control-group">
                            <label for="logFile">File:</label>
                            <select id="logFile" onchange="bsync.loadLog()"></select>
                        </div>
                        <div class="control-group">
                            <label for="searchText">Search:</label>
                            <input type="text" id="searchText" placeholder="Search..." onkeyup="bsync.filterLines()">
                        </div>
                        <div class="control-group">
                            <label><input type="checkbox" id="problemsOnly" onchange="bsync.filterLines()"> Problems only</label>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="bsync.loadLog()">↻ Reload</button>
                    </div>
                    <div id="stats" class="stats" style="margin-top:8px;"></div>
                    <div id="logContainer" class="log-container" style="margin-top:8px;"></div>
                </div>
            </div>
        </div>

        <!-- ════════════════════════════════════════════════════════
             TAB 2: SYNC FINGERPRINT
        ════════════════════════════════════════════════════════ -->
        <div id="tab-fingerprint" class="tab-panel">

            <!-- Source + Target on same row -->
            <div class="fp-machines-row">

                <!-- Source machine -->
                <div class="card fp-card-source">
                    <div class="card-title">
                        <span class="section-num">1</span>
                        Source Device
                    </div>
                    <div class="form-group" style="margin-bottom:10px;">
                        <label>Master / Source Machine</label>
                        <select id="masterMachine" style="width:100%;">
                            <option value="">-- Loading machines... --</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" style="width:100%;" onclick="bsync.loadMasterUsers()">
                        🔄 Load users from source machine
                    </button>
                    <div id="masterLoadStatus" style="margin-top:10px;"></div>
                </div>

                <!-- Target machines + ERP option -->
                <div class="card fp-card-targets">
                    <div class="card-title">
                        <span class="section-num">2</span>
                        Destinations
                    </div>

                    <!-- Sync to ERPNext toggle -->
                    <label style="display:flex;align-items:center;gap:10px;padding:10px 12px;
                                  border:1px solid var(--border);border-radius:var(--radius-sm);
                                  margin-bottom:10px;cursor:pointer;background:var(--bg);">
                        <input type="checkbox" id="fpSyncToErp" checked
                            style="width:16px;height:16px;accent-color:var(--primary);cursor:pointer;">
                        <div>
                            <div style="font-size:13px;font-weight:600;color:var(--text);">Sync to ERPNext</div>
                            <div style="font-size:11px;color:var(--text-3);">Save fingerprints data into Employee -
                                Fingerprints table</div>
                        </div>
                    </label>

                    <!-- Target devices -->
                    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
                        <div
                            style="font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:var(--text-3);flex:1;">
                            Target Devices
                        </div>
                        <button class="btn btn-sm btn-secondary" style="padding:2px 8px;font-size:11px;"
                            onclick="bsync.selectAllTargets(true)">All</button>
                        <button class="btn btn-sm btn-secondary" style="padding:2px 8px;font-size:11px;"
                            onclick="bsync.selectAllTargets(false)">None</button>
                    </div>
                    <div id="targetMachineList" class="machine-list" style="max-height:200px;">
                        <div class="loading" style="padding:15px;">
                            <div class="spinner"></div>
                            <p>Loading...</p>
                        </div>
                    </div>
                </div>

            </div>

            <!-- Section 3: Filter Employee -->
            <div class="card">
                <div class="card-title">
                    <span class="section-num">3</span>
                    Filter Employees from ERPNext
                    <span style="font-size:12px;color:var(--text-3);font-weight:400;">(optional — leave blank to show
                        all)</span>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Employee ID</label>
                        <input type="text" id="filterEmpId" placeholder="TIQN-0001">
                    </div>
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" id="filterEmpName" placeholder="Enter name">
                    </div>
                    <div class="form-group">
                        <label>Fingerprint ID</label>
                        <input type="text" id="filterDeviceId" placeholder="001">
                    </div>
                    <div class="form-group">
                        <label>Date of Joining ≥</label>
                        <input type="date" id="filterJoinDate">
                    </div>
                    <button class="btn btn-primary" onclick="bsync.applyEmployeeFilter()">🔍 Filter</button>
                    <button class="btn btn-secondary" onclick="bsync.clearEmployeeFilter()">✕ Clear</button>
                </div>
                <div id="filterStatus" style="margin-top:8px;"></div>
            </div>

            <!-- Section 4: User list -->
            <div class="card">
                <div class="card-title">
                    <span class="section-num">4</span>
                    Users on Source Machine
                    <div style="margin-left:auto; display:flex; gap:8px;">
                        <button class="btn btn-sm btn-secondary" onclick="bsync.selectAllUsers(true)">All</button>
                        <button class="btn btn-sm btn-secondary" onclick="bsync.selectAllUsers(false)">None</button>
                    </div>
                </div>
                <div id="userTableStats" class="stats" style="margin-bottom:12px;">No data loaded yet</div>
                <div id="userTableWrap">
                    <div class="no-logs">
                        <p>👆 Click "Load users from source machine" above</p>
                    </div>
                </div>
            </div>

            <!-- Sync Button -->
            <div style="text-align:center; margin-bottom:20px;">
                <button class="btn btn-success" id="syncBtn" onclick="bsync.startSync()"
                    style="padding:12px 32px; font-size:15px;" disabled>
                    ▶ Sync Fingerprints
                </button>
                <div id="syncSummary" style="margin-top:8px; color:var(--text-2); font-size:13px;"></div>
            </div>

            <!-- Section 5: Progress -->
            <div class="card progress-section" id="progressSection">
                <div class="card-title">⏳ Sync Progress</div>
                <div id="progressPhase" style="font-size:13px; color:var(--text-2); margin-bottom:12px;"></div>
                <div id="machineProgressList"></div>
                <div class="result-log" id="resultLog"></div>
            </div>

        </div><!-- end tab-fingerprint -->

        <!-- ════════════════════════════════════════════════════════
             TAB 4.1: ERP → ATTENDANCE MACHINES
        ════════════════════════════════════════════════════════ -->
        <div id="tab-fp41" class="tab-panel">

            <div class="card">
                <div class="card-title"><span class="section-num">1</span> Select Employees to Sync</div>
                <div class="form-row" style="margin-bottom:10px;">
                    <div class="form-group">
                        <label>Scope</label>
                        <select id="fp41Scope" onchange="bsync.onFp41ScopeChange()">
                            <option value="all">All Active Employees</option>
                            <option value="date">Employees joined from date ≥</option>
                            <option value="manual">Manual input (Employee IDs)</option>
                        </select>
                    </div>
                    <div class="form-group" id="fp41DateGroup" style="display:none;">
                        <label>Date of Joining ≥</label>
                        <input type="date" id="fp41JoinDate">
                    </div>
                </div>
                <div id="fp41ManualGroup" style="display:none;margin-bottom:10px;">
                    <label
                        style="font-size:13px;font-weight:500;color:var(--text-2);display:block;margin-bottom:4px;">Employee
                        IDs (one per line)</label>
                    <textarea id="fp41ManualIds" class="form-control" rows="4"
                        placeholder="TIQN-0001&#10;TIQN-0002&#10;TIQN-0003"></textarea>
                </div>
                <button class="btn btn-primary" onclick="bsync.fp41LoadEmployees()">🔍 Load Employees</button>
                <div id="fp41EmpStatus" style="margin-top:8px;font-size:13px;"></div>
                <div id="fp41EmpTableWrap" style="display:none;margin-top:12px;">
                    <div class="all-info-table-wrap">
                        <table id="fp41EmpTable">
                            <thead>
                                <tr>
                                    <th style="width:32px;">#</th>
                                    <th>Employee</th>
                                    <th>Employee Name</th>
                                    <th>Attendance Device ID</th>
                                    <th>Group</th>
                                </tr>
                            </thead>
                            <tbody id="fp41EmpTableBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title"><span class="section-num">2</span> Select Target Machines</div>
                <div style="display:flex;gap:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap;">
                    <span id="fp41MachineScopeWrap" style="display:none;align-items:center;gap:6px;margin-right:8px;">
                        <strong style="font-size:13px;color:var(--text-2);">Machines:</strong>
                        <select id="fp41MachineScope" onchange="bsync.fp41MachineScopeChange()" style="min-width:0;">
                            <option value="attendance">Attendance only</option>
                            <option value="door">Door control only</option>
                            <option value="all">All</option>
                        </select>
                    </span>
                    <button class="btn btn-sm btn-secondary" onclick="bsync.fp41SelectAllMachines(true)">All</button>
                    <button class="btn btn-sm btn-secondary" onclick="bsync.fp41SelectAllMachines(false)">None</button>
                </div>
                <div id="fp41MachineList" class="machine-list">
                    <div class="loading" style="padding:15px;">
                        <div class="spinner"></div>
                        <p>Loading machines...</p>
                    </div>
                </div>
            </div>

            <div style="text-align:center;margin-bottom:20px;">
                <button class="btn btn-success" id="fp41SyncBtn" onclick="bsync.fp41StartSync()"
                    style="padding:12px 32px;font-size:15px;" disabled>
                    ▶ Sync ERP → Machines
                </button>
                <div id="fp41SyncSummary" style="margin-top:8px;color:var(--text-2);font-size:13px;"></div>
            </div>

            <div class="card progress-section" id="fp41ProgressSection">
                <div class="card-title">⏳ Sync Progress — ERP → Machines</div>
                <div id="fp41ProgressPhase" style="font-size:13px;color:var(--text-2);margin-bottom:8px;"></div>
                <div class="progress-bar-wrap" style="margin-bottom:10px;">
                    <div class="progress-bar" id="fp41ProgressBar" style="width:0%;"></div>
                </div>
                <div class="result-log" id="fp41ResultLog"></div>
            </div>

        </div><!-- end tab-fp41 -->

        <!-- ════════════════════════════════════════════════════════
             TAB 4.3: REMOVE LEFT STAFF FROM ATTENDANCE MACHINES
        ════════════════════════════════════════════════════════ -->
        <div id="tab-del43" class="tab-panel">

            <div class="card">
                <div class="alert alert-warning" style="margin-bottom:14px;">
                    <strong>⚠ Important notes:</strong><br>
                    • <strong>Active</strong> employees will <strong>NEVER</strong> be deleted.<br>
                    • Fingerprint data in <strong>ERPNext is NEVER deleted</strong> — only removed from the attendance
                    device.<br>
                    • Only <strong>resigned</strong> employees past the configured delay threshold are removed.
                </div>
                <div class="form-row" style="flex-wrap:wrap;align-items:flex-end;gap:16px;">
                    <div class="form-group">
                        <label>Days to wait after <code>relieving_date</code></label>
                        <select id="del43DelayDays">
                            <option value="15">15 days</option>
                            <option value="30">30 days</option>
                            <option value="45" selected>45 days (default)</option>
                            <option value="60">60 days</option>
                            <option value="90">90 days</option>
                        </select>
                    </div>
                    <div class="form-group" style="justify-content:flex-end;padding-bottom:2px;">
                        <label
                            style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:normal;margin:0;">
                            <input type="checkbox" id="del43IncludeUnmatched"
                                style="width:15px;height:15px;accent-color:var(--primary);">
                            <span style="font-size:13px;">Also delete user_ids <strong>not matched</strong> to any
                                employee in ERPNext</span>
                        </label>
                    </div>
                </div>
                <div style="margin-top:14px;display:flex;gap:10px;align-items:center;">
                    <button class="btn btn-primary" id="del43ScanBtn" onclick="bsync.del43Scan()">🔍 Scan All
                        Machines</button>
                    <span id="del43ScanStatus" style="font-size:13px;color:var(--text-2);"></span>
                </div>
            </div>

            <div id="del43PreviewSection" style="display:none;">
                <div class="card">
                    <div class="card-title">📋 Scan Results — Confirm Deletion</div>
                    <div id="del43ScanSummary" style="margin-bottom:12px;"></div>
                    <div id="del43PreviewTable"></div>
                    <div style="margin-top:14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                        <button class="btn btn-danger" id="del43DeleteBtn" onclick="bsync.del43Delete()">🗑 Delete Selected
                            Users</button>
                        <button class="btn btn-secondary" onclick="bsync.del43ResetPreview()">✕ Cancel</button>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">🎯 Delete a Specific Employee</div>
                <div style="font-size:13px;color:var(--text-2);margin-bottom:12px;">
                    Remove one specific employee's <code>user_id</code> from the attendance devices —
                    fingerprint data in ERPNext is <strong>never</strong> deleted.
                    <strong>Active</strong> employees cannot be deleted.
                </div>
                <div class="form-row" style="align-items:flex-end;gap:12px;flex-wrap:wrap;">
                    <div class="form-group" style="flex:1;min-width:240px;">
                        <label>Employee ID / Device ID / Name</label>
                        <input type="text" id="del43FindInput" placeholder="e.g. HR-EMP-00012, 1042, or Nguyen Van A"
                            onkeydown="if(event.key==='Enter')bsync.del43FindEmp();">
                    </div>
                    <button class="btn btn-primary" id="del43FindBtn" onclick="bsync.del43FindEmp()">🔍 Find</button>
                    <span id="del43FindStatus" style="font-size:13px;color:var(--text-2);"></span>
                </div>
                <div id="del43FindResult" style="margin-top:14px;display:none;"></div>
            </div>

            <div class="card progress-section" id="del43ProgressSection">
                <div class="card-title">⏳ Deletion Progress</div>
                <div id="del43ProgressPhase" style="font-size:13px;color:var(--text-2);margin-bottom:8px;"></div>
                <div class="progress-bar-wrap" style="margin-bottom:10px;">
                    <div class="progress-bar" id="del43ProgressBar" style="width:0%;"></div>
                </div>
                <div class="result-log" id="del43ResultLog"></div>
            </div>

        </div><!-- end tab-del43 -->

        <!-- ════════════════════════════════════════════════════════
             TAB MACHINES MANAGEMENT
        ════════════════════════════════════════════════════════ -->
        <div id="tab-machines" class="tab-panel">

            <div class="global-actions toolbar">
                <span id="machinesScopeWrap" style="display:none;align-items:center;gap:6px;margin-right:8px;">
                    <strong style="font-size:13px;color:var(--text-2);">Machines:</strong>
                    <select id="machinesScope" onchange="bsync.machinesScopeChange()" style="min-width:0;">
                        <option value="attendance">Attendance only</option>
                        <option value="door">Door control only</option>
                        <option value="all">All</option>
                    </select>
                </span>
                <strong style="font-size:13px;color:var(--text-2);margin-right:4px;">Bulk actions:</strong>
                <button class="btn btn-primary btn-sm" onclick="bsync.machinesRefresh()">🔄 Refresh</button>
                <button class="btn btn-sm btn-info-sm" onclick="bsync.machinesSyncTimeAll()">🕐 Sync Time All</button>
                <button class="btn btn-sm btn-danger-sm" onclick="bsync.machinesRebootAll()">🔁 Reboot All ⚠</button>
                <button class="btn btn-sm" style="background:#7c3aed;color:#fff;" onclick="bsync.machinesLoadAllInfo()">📊
                    Load Info All</button>
                <button class="btn btn-sm btn-success" onclick="bsync.machinesLoadUsersAll()">👥 Users All</button>
                <span id="machinesGlobalStatus" style="font-size:13px;color:var(--text-2);margin-left:8px;"></span>
            </div>

            <div id="machinesLoadingArea" class="loading">
                <div class="spinner"></div>
                <p style="margin-top:8px;">Loading attendance machines...</p>
            </div>

            <div id="machineCardsGrid" class="machine-grid" style="display:none;"></div>

            <!-- All-machines info table -->
            <div id="allMachinesInfoSection" style="display:none;margin-top:18px;">
                <div class="card">
                    <div class="card-title" style="display:flex;align-items:center;justify-content:space-between;">
                        <span>📊 All Machines — Hardware Info</span>
                        <span id="allInfoTimestamp"
                            style="font-size:11px;color:var(--text-3);font-weight:normal;"></span>
                    </div>
                    <div class="all-info-table-wrap">
                        <table id="allMachinesInfoTable">
                            <thead>
                                <tr>
                                    <th>Machine</th>
                                    <th>IP : Port</th>
                                    <th>Firmware</th>
                                    <th>Serial</th>
                                    <th>Platform</th>
                                    <th>FP Version</th>
                                    <th>Users</th>
                                    <th>Fingerprints</th>
                                    <th>Records</th>
                                    <th>Device Time</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody id="allMachinesInfoBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- Users stored on the machines -->
            <div id="machineUsersSection" style="display:none;margin-top:18px;">
                <div class="card">
                    <div class="card-title" style="display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;">
                        <span>👥 Users on Machines</span>
                        <span id="muInfo" style="font-size:11px;color:var(--text-3);font-weight:normal;"></span>
                    </div>
                    <div class="toolbar" style="margin-bottom:10px;">
                        <select id="muMachine" onchange="bsync.muMachineChange()" style="min-width:220px;"></select>
                        <input type="text" id="muSearch" placeholder="Search user ID, name, employee..." oninput="bsync.muRender()">
                        <select id="muStatus" onchange="bsync.muRender()" style="min-width:0;">
                            <option value="">All ERP statuses</option>
                            <option value="Active">Active</option>
                            <option value="Left">Left</option>
                            <option value="other">Other status</option>
                            <option value="none">Not in ERP</option>
                        </select>
                        <select id="muFingers" onchange="bsync.muRender()" style="min-width:0;" title="Fingerprint templates on the device">
                            <option value="">All fingers</option>
                            <option value="0">No fingerprint</option>
                            <option value="1">Only 1 finger</option>
                            <option value="differs">Differs between machines</option>
                        </select>
                        <span id="muCount" style="font-size:13px;color:var(--text-2);"></span>
                        <button class="btn btn-sm btn-danger-sm" id="muDeleteBtn" onclick="bsync.muDelete()" style="margin-left:auto;" disabled>🗑 Delete selected</button>
                        <button class="btn btn-sm btn-primary" id="muDownloadBtn" onclick="bsync.muDownload()">⬇ Download xlsx</button>
                    </div>
                    <div class="del-preview-wrap" style="max-height:520px;">
                        <table id="muTable">
                            <thead id="muHead"></thead>
                            <tbody id="muBody"></tbody>
                        </table>
                    </div>
                </div>
            </div>

        </div><!-- end tab-machines -->

        <!-- ════════════════════════════════════════════════════════
             TAB 6: MANUAL RE-SYNC (ported from CLI tool manual menu)
        ════════════════════════════════════════════════════════ -->
        <div id="tab-resync" class="tab-panel">

            <div class="card">
                <div class="card-title"><span class="section-num">1</span> 🔁 Re-sync Device → ERPNext (date range)
                </div>
                <div style="font-size:12.5px;color:var(--text-2);margin-bottom:10px;">
                    Re-read attendance logs directly from the selected machines and push them to ERPNext.
                    Existing checkins are skipped automatically (duplicate-safe).
                </div>
                <div style="display:flex;gap:8px;margin-bottom:8px;">
                    <button class="btn btn-sm btn-secondary" onclick="bsync.rsSelectAllMachines(true)">All</button>
                    <button class="btn btn-sm btn-secondary" onclick="bsync.rsSelectAllMachines(false)">None</button>
                </div>
                <div id="rsMachineList" class="machine-list" style="margin-bottom:10px;">
                    <div class="loading" style="padding:15px;">
                        <div class="spinner"></div>
                        <p>Loading machines...</p>
                    </div>
                </div>
                <div class="form-row" style="margin-bottom:10px;">
                    <div class="form-group"><label>From date</label><input type="date" id="rsDevFrom"></div>
                    <div class="form-group"><label>To date</label><input type="date" id="rsDevTo"></div>
                </div>
                <button class="btn btn-primary" id="rsDevBtn" onclick="bsync.rsRunDeviceResync()">▶ Re-sync from
                    devices</button>
            </div>

            <div class="card">
                <div class="card-title"><span class="section-num">2</span> 🗄 Sync MongoDB → ERPNext (date range)</div>
                <div style="font-size:12.5px;color:var(--text-2);margin-bottom:10px;">
                    Sync attendance checkins from MongoDB (AttLog) for a date range. Duplicate-safe.
                    Does not touch the auto-sync watermark.
                </div>
                <div class="form-row" style="margin-bottom:10px;">
                    <div class="form-group"><label>From date</label><input type="date" id="rsMongoFrom"></div>
                    <div class="form-group"><label>To date</label><input type="date" id="rsMongoTo"></div>
                </div>
                <button class="btn btn-primary" id="rsMongoBtn" onclick="bsync.rsRunMongoResync()">▶ Sync from
                    MongoDB</button>
            </div>

            <div class="card">
                <div class="card-title"><span class="section-num">3</span> 📋 Sync OT MongoDB → ERPNext</div>
                <div style="font-size:12.5px;color:var(--text-2);margin-bottom:10px;">
                    Create Overtime Registrations from MongoDB (OtRegister) for the OT date range.
                    Rows are compared one by one: rows missing from an existing request are added back to it
                    (e.g. after Delete OT), rows that already exist are skipped.
                </div>
                <div class="form-row" style="margin-bottom:10px;">
                    <div class="form-group"><label>OT date from</label><input type="date" id="rsOtFrom"></div>
                    <div class="form-group"><label>OT date to</label><input type="date" id="rsOtTo"></div>
                </div>
                <button class="btn btn-primary" id="rsOtBtn" onclick="bsync.rsRunOtSync()">▶ Sync OT from MongoDB</button>
            </div>

            <div class="card" id="rsDeleteOtCard" style="display:none;border:1px solid var(--danger);">
                <div class="card-title" style="color:#c0392b;">⚠️ Delete OT in ERPNext — System Manager only</div>
                <div class="alert alert-warning" style="margin-bottom:10px;font-size:12.5px;">
                    Deletes Overtime Registration detail rows whose date falls in the range (via the Frappe ORM —
                    documents are trimmed or deleted properly, submitted docs with rows outside the range are skipped).
                    Run <strong>Preview</strong> first, then type <strong>DELETE</strong> to enable the delete button.
                </div>
                <div class="form-row" style="margin-bottom:10px;">
                    <div class="form-group"><label>From date</label><input type="date" id="rsDelFrom"></div>
                    <div class="form-group"><label>To date</label><input type="date" id="rsDelTo"></div>
                </div>
                <button class="btn btn-sm btn-secondary" onclick="bsync.rsPreviewDeleteOt()">🔍 Preview (dry-run)</button>
                <div id="rsDelPreview" style="margin-top:10px;font-size:13px;"></div>
                <div id="rsDelConfirmZone" style="display:none;margin-top:10px;">
                    <label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px;">
                        Type <strong>DELETE</strong> to confirm:</label>
                    <div style="display:flex;gap:8px;align-items:center;">
                        <input type="text" id="rsDelConfirm" oninput="bsync.rsDelConfirmInput()" autocomplete="off"
                            style="width:160px;padding:6px 10px;border:1px solid var(--border-2);border-radius:6px;">
                        <button class="btn btn-sm btn-danger-sm" id="rsDelBtn" onclick="bsync.rsRunDeleteOt()" disabled>🗑
                            Delete OT</button>
                    </div>
                </div>
            </div>

            <div class="card progress-section" id="rsProgressSection">
                <div class="card-title">⏳ Job Progress</div>
                <div id="rsProgressPhase" style="font-size:13px;color:var(--text-2);margin-bottom:8px;"></div>
                <div class="progress-bar-wrap" style="margin-bottom:10px;">
                    <div class="progress-bar" id="rsProgressBar" style="width:0%;"></div>
                </div>
                <div class="result-log" id="rsResultLog"></div>
            </div>

        </div><!-- end tab-resync -->


    </div><!-- end main-wrap -->

    
</div>`;

frappe.pages["biometric-sync"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Biometric Sync"),
        single_column: true,
    });
    $(page.body).html(BSYNC_HTML);
    const root = page.body.find(".bsync").get(0);
    if (!frappe.user.has_role("System Manager")) {
        root.querySelectorAll("[data-sm-only]").forEach(el => el.remove());
    }
    bsync.setup(root);
};

bsync.setup = function (root) {

        // ── Hộp thoại frappe thay alert/confirm gốc của trình duyệt ──────────────────
        function _bsyncHtml(msg) {
            return frappe.utils.escape_html(String(msg)).replace(/\n/g, '<br>');
        }
        function bsyncAlert(msg) {
            frappe.msgprint({ message: _bsyncHtml(msg), indicator: 'orange' });
        }
        function bsyncConfirm(msg) {
            return new Promise(resolve => {
                // frappe.confirm tự gọi nhánh "không" khi đóng bằng X / Esc
                frappe.confirm(_bsyncHtml(msg), () => resolve(true), () => resolve(false));
            });
        }


        // ─── CSRF token — injected from Python context via Jinja ─────────────────
        
        window.is_system_manager = frappe.user.has_role("System Manager") ? 1 : 0;

        // ─── Helper: parse Frappe error response ──────────────────────────────────────
        function _parseFrappeError(data, httpStatus) {
            let msg = '';
            try { msg = JSON.parse(JSON.parse(data._server_messages || '[]')[0]).message; } catch { }
            return msg || data.exc_type || data.exc || `HTTP ${httpStatus}`;
        }

        // ─── GET helper (read-only, no CSRF needed) ───────────────────────────────────
        // ─── Peak Times guard ────────────────────────────────────────────────────────
        // These calls lock attendance machines for seconds (reboot: ~1 min) — inside a
        // Peak Times window of Attendance Machine Setting ask first. One answer covers
        // the next 2 minutes so per-employee loops (Tab 3) do not ask again and again.
        const PEAK_LOCKING_METHODS = new Set([
            'customize_erpnext.network.biometric.biometric_sync.get_master_device_users',
            'customize_erpnext.network.biometric.biometric_sync.sync_fingerprints',
            'customize_erpnext.network.biometric.biometric_sync.get_left_employees_on_machines',
            'customize_erpnext.network.biometric.biometric_sync.find_employee_on_machines',
            'customize_erpnext.network.biometric.biometric_sync.delete_users_from_machines',
            'customize_erpnext.network.biometric.biometric_sync.machine_reboot',
            'customize_erpnext.network.biometric.biometric_sync.machine_get_users',
            'customize_erpnext.network.biometric.fingerprint.sync_employee_to_single_machine',
            'customize_erpnext.network.biometric.fingerprint.sync_employees_to_machine_batch',
            'customize_erpnext.network.biometric.resync.resync_device_logs',
        ]);
        const PEAK_ANSWER_MS = 2 * 60 * 1000;
        let _peakAnswer = null;   // { ok: bool, until: ms }
        let _peakAsking = null;   // in-flight question (parallel "All machines" calls share it)

        async function confirmPeakIfNeeded(method) {
            if (!PEAK_LOCKING_METHODS.has(method)) return;
            if (_peakAnswer && Date.now() < _peakAnswer.until) {
                if (_peakAnswer.ok) return;
                throw new Error(__('Cancelled: peak check-in time'));
            }
            if (!_peakAsking) {
                _peakAsking = (async () => {
                    let st = null;
                    try { st = await callGet('customize_erpnext.network.biometric.device_log_sync.get_peak_status'); }
                    catch (e) { return true; }   // status unknown: do not block the user's action
                    if (!st || !st.in_peak) return true;
                    return window.confirm(__(
                        'Peak check-in time ({0}–{1}).\n\nThis action locks the attendance machine(s) for several seconds (reboot: about 1 minute) and employees cannot clock in meanwhile.\n\nContinue anyway?',
                        [st.start, st.end]));
                })().finally(() => { setTimeout(() => { _peakAsking = null; }, 0); });
            }
            const ok = await _peakAsking;
            _peakAnswer = { ok, until: Date.now() + PEAK_ANSWER_MS };
            if (!ok) throw new Error(__('Cancelled: peak check-in time'));
        }

        async function callGet(method, args) {
            await confirmPeakIfNeeded(method);
            const params = new URLSearchParams();
            for (const [k, v] of Object.entries(args || {})) {
                if (v !== null && v !== undefined && v !== '') params.set(k, String(v));
            }
            const qs = params.toString();
            const url = `/api/method/${method}` + (qs ? `?${qs}` : '');
            const res = await fetch(url, { credentials: 'same-origin' });
            if (res.status === 403 || res.status === 401) { location.reload(); throw new Error('Session expired'); }
            let data;
            try { data = await res.json(); }
            catch (e) { throw new Error(`HTTP ${res.status} — response is not JSON`); }
            if (!res.ok || data.exc || data.exc_type) throw new Error(_parseFrappeError(data, res.status));
            if (data.message === undefined) throw new Error(`Server returned empty response (HTTP ${res.status})`);
            return data.message;
        }

        // ─── POST helper (write operations, CSRF required) ────────────────────────────
        async function callPost(method, args) {
            await confirmPeakIfNeeded(method);
            const fd = new FormData();
            fd.append('csrf_token', frappe.csrf_token);
            for (const [k, v] of Object.entries(args || {})) {
                fd.append(k, v === null || v === undefined ? '' : String(v));
            }
            const res = await fetch(`/api/method/${method}`, {
                method: 'POST', credentials: 'same-origin', body: fd
            });
            if (res.status === 403 || res.status === 401) { location.reload(); throw new Error('Session expired'); }
            let data;
            try { data = await res.json(); }
            catch (e) { throw new Error(`HTTP ${res.status} — response is not JSON`); }
            if (!res.ok || data.exc || data.exc_type) throw new Error(_parseFrappeError(data, res.status));
            if (data.message === undefined) throw new Error(`Server returned empty response (HTTP ${res.status})`);
            return data.message;
        }

        // ─── Tab switching ────────────────────────────────────────────────────────────
        function switchTab(tabId) {
            root.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            root.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            const panel = document.getElementById(tabId);
            if (panel) panel.classList.add('active');
            const btn = root.querySelector(`.tab-btn[data-tab="${tabId}"]`);
            if (btn) btn.classList.add('active');
            // Lazy actions on tab open
            if (tabId === 'tab-machines' && !_machinesLoaded) loadMachineCards();
            if (tabId === 'tab-resync') rsInitTab();
            if (tabId === 'tab-fp41' && _allMachines.length) fp41RenderMachines();
        }

        function escapeHtml(text) {
            const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
            return String(text).replace(/[&<>"']/g, m => map[m]);
        }

        // ════════════════════════════════════════════════════════════════════════════
        // TAB 1 — LOG VIEWER
        // ════════════════════════════════════════════════════════════════════════════
        let allLines = [];        // raw log, newest first
        let _rawLogLoaded = false;

        // ── Status table (last cycle of the automatic pull, stored by the job) ──────
        function _ago(iso, nowIso) {
            if (!iso) return '';
            const min = Math.max(0, Math.round((new Date(nowIso.replace(' ', 'T')) - new Date(iso.replace(' ', 'T'))) / 60000));
            return min < 1 ? 'just now' : `${min} min ago`;
        }

        function _hm(iso) { return iso ? iso.slice(0, 19).replace('T', ' ') : '—'; }

        async function loadSyncStatus() {
            const sum = document.getElementById('syncStatusSummary');
            try {
                renderSyncStatus(await callGet('customize_erpnext.network.biometric.log_viewer.get_sync_status'));
            } catch (e) {
                sum.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(e.message)}</span>`;
            }
        }

        function renderSyncStatus(st) {
            const parts = [
                st.auto_sync_logs ? '<b style="color:#16a34a;">● Auto pull ON</b>' : '<b style="color:#dc3545;">● Auto pull OFF</b>',
                st.last_cycle ? `Last cycle: <b>${escapeHtml(_hm(st.last_cycle).slice(11))}</b> (${_ago(st.last_cycle, st.now)})` : 'Last cycle: —',
            ];
            if (st.peak) parts.push(`<b style="color:#b45309;">Peak now ${st.peak.start}–${st.peak.end} — machines are not read</b>`);
            else if (st.next_peak) parts.push(`Next peak: ${st.next_peak.start}–${st.next_peak.end}`);
            document.getElementById('syncStatusSummary').innerHTML = parts.join(' &nbsp;·&nbsp; ');

            document.getElementById('syncStatusAlert').innerHTML = st.stalled
                ? `<div class="alert alert-warning" style="margin-top:8px;">⚠ No cycle has read the machines for ${st.idle_minutes} min (peak windows excluded). Check the "biometric" worker and the scheduler.</div>`
                : '';

            const rows = (st.machines || []).map(m => {
                let status, cls = '';
                if (!m.in_last_cycle) status = '<span style="color:#6b7280;">not in last cycle</span>';
                else if (m.skip_reason) status = `<span style="color:#6b7280;">skipped (${escapeHtml(m.skip_reason)})</span>`;
                else if (m.read === null || m.read === undefined) {
                    cls = 'style="background:#fef2f2;"';
                    status = `<span class="badge-unmatched">❌ ${m.consecutive_failures ? m.consecutive_failures + '× ' : ''}${escapeHtml(m.error || 'failed')}</span>`;
                } else if (!m.ok) {
                    cls = 'style="background:#fef2f2;"';
                    status = `<span class="badge-unmatched">❌ ${escapeHtml(m.error || 'error')}</span>`;
                } else if (m.deferred) status = `<span style="color:#b45309;">⏸ ${escapeHtml(m.deferred)}</span>`;
                else status = '<span class="badge-matched">✅ OK</span>';
                const num = v => (v === null || v === undefined) ? '—' : Number(v).toLocaleString('en-US');
                return `<tr ${cls}>
                    <td><b>${escapeHtml(m.machine)}</b></td>
                    <td>${escapeHtml(_hm(m.latest_checkin))}</td>
                    <td>${num(m.read)}</td>
                    <td>${num(m.inserted)}</td>
                    <td>${m.seconds === null || m.seconds === undefined ? '—' : m.seconds + ' s'}</td>
                    <td>${status}</td>
                </tr>`;
            });
            document.getElementById('syncStatusRows').innerHTML = rows.join('') ||
                '<tr><td colspan="6" style="color:#6b7280;">No enabled attendance machine</td></tr>';

            const mongo = (st.mongo || []).map(x => `${escapeHtml((x.at || '').slice(5, 16))} · ${escapeHtml(x.text)}`);
            document.getElementById('mongoStatus').innerHTML = mongo.length
                ? `<b>MongoDB (daily 18:00):</b><br>${mongo.join('<br>')}` : '<b>MongoDB (daily 18:00):</b> no run yet';
        }

        // ── Raw log (collapsed) ─────────────────────────────────────────────────────
        function toggleRawLog() {
            const body = document.getElementById('rawLogBody');
            const open = body.style.display === 'none';
            body.style.display = open ? 'block' : 'none';
            document.getElementById('rawLogArrow').textContent = open ? '▾' : '▸';
            if (open && !_rawLogLoaded) loadLogFiles();
        }

        async function loadLogFiles() {
            const sel = document.getElementById('logFile');
            try {
                const files = await callGet('customize_erpnext.network.biometric.log_viewer.get_log_files');
                sel.innerHTML = files.map(f => `<option value="${escapeHtml(f.file)}">${escapeHtml(f.label)}</option>`).join('');
                _rawLogLoaded = true;
                if (files.length) loadLog();
                else document.getElementById('logContainer').innerHTML = '<div class="no-logs"><p>No log yet</p></div>';
            } catch (e) {
                sel.innerHTML = `<option value="">❌ ${escapeHtml(e.message)}</option>`;
            }
        }

        async function loadLog() {
            const logFile = document.getElementById('logFile').value;
            const box = document.getElementById('logContainer');
            if (!logFile) return;
            box.innerHTML = '<div class="no-logs"><p>Loading...</p></div>';
            try {
                const msg = await callGet('customize_erpnext.network.biometric.log_viewer.get_log_content', { log_file: logFile });
                allLines = msg.lines || [];
                filterLines();
            } catch (e) {
                box.innerHTML = `<div class="no-logs"><p style="color:#dc3545;">❌ ${escapeHtml(e.message)}</p></div>`;
            }
        }

        // a cycle row with something to look at: failure, insert error, deferral, stall, ERROR line
        const PROBLEM_RE = /FAILED|errors=[1-9]|deferred=|STALLED|\bERROR\b|[1-9]\d* errors|[1-9]\d* failed/;

        function filterLines() {
            const q = document.getElementById('searchText').value.toLowerCase();
            const problemsOnly = document.getElementById('problemsOnly').checked;
            const box = document.getElementById('logContainer');
            let lines = allLines;
            if (problemsOnly) lines = lines.filter(l => PROBLEM_RE.test(l));
            if (q) lines = lines.filter(l => l.toLowerCase().includes(q));
            box.innerHTML = lines.length
                ? lines.map(l => `<div class="log-line${PROBLEM_RE.test(l) ? ' error' : ''}">${escapeHtml(l)}</div>`).join('')
                : '<div class="no-logs"><p>No matching lines</p></div>';
            document.getElementById('stats').textContent = `${lines.length} / ${allLines.length} lines (newest first, last 500)`;
        }

        // ════════════════════════════════════════════════════════════════════════════
        // TAB 2 — SYNC FINGERPRINT
        // ════════════════════════════════════════════════════════════════════════════

        let _allMachines = [];       // enabled attendance machines (Tab 2 + Tab 3 default)
        let _fp41AllMachines = [];   // + door controllers (server adds them only for Door Control)
        let _masterUsers = [];       // users returned from master device
        let _filteredDeviceIds = null; // set of device IDs from ERPNext filter, or null (no filter)
        let _pollTimer = null;

        // ── Load machines ─────────────────────────────────────────────────────────────
        async function loadMachinesForFingerprint() {
            try {
                // include_door: the server adds door controllers only for the Door Control
                // role. Tab 2 (device → device) never uses them; Tab 3 offers them by scope.
                const msg = await callGet('customize_erpnext.network.biometric.fingerprint.get_enabled_attendance_machines', { include_door: 1 });
                if (!msg.success) throw new Error(msg.message);
                _fp41AllMachines = msg.machines || [];
                _allMachines = _fp41AllMachines.filter(m => !m.is_door_control);
                renderMasterDropdown();
                renderTargetMachines(null); // null = no master selected yet
                fp41RenderMachines();       // also populate 4.1 machine list
            } catch (e) {
                document.getElementById('targetMachineList').innerHTML =
                    `<div class="alert alert-danger">❌ Failed to load machines: ${escapeHtml(e.message)}</div>`;
            }
        }

        function renderMasterDropdown() {
            const sel = document.getElementById('masterMachine');
            sel.innerHTML = '<option value="">-- Select source machine --</option>';
            _allMachines.forEach(m => {
                const o = document.createElement('option');
                o.value = m.name;
                const statusIcon = m.connection_status === 'online' ? '🟢' : '🔴';
                o.textContent = `${statusIcon} ${m.name} — ${m.device_name} (${m.ip_address})`;
                sel.appendChild(o);
            });
            sel.addEventListener('change', () => renderTargetMachines(sel.value));
            renderTargetMachines(sel.value);
        }

        function renderTargetMachines(masterName) {
            const wrap = document.getElementById('targetMachineList');
            const targets = _allMachines.filter(m => m.name !== masterName);
            if (!targets.length) {
                wrap.innerHTML = '<div class="alert alert-info">No target machines (need at least 2 enabled machines)</div>';
                updateSyncButton();
                return;
            }
            wrap.innerHTML = targets.map(m => {
                const isOnline = m.connection_status === 'online';
                const statusIcon = isOnline ? '🟢' : '🔴';
                return `
        <label class="machine-item">
            <input type="checkbox" class="target-machine-cb" value="${escapeHtml(m.name)}" checked>
            <span class="machine-item-label">
                ${statusIcon} <strong>${escapeHtml(m.name)}</strong> — ${escapeHtml(m.device_name)}
                <span style="color:var(--text-3);">(${escapeHtml(m.ip_address)})</span>
            </span>
            ${m.response_time > 0 ? `<span class="badge">${m.response_time}ms</span>` : ''}
        </label>`;
            }).join('');
            updateSyncButton();
        }

        function selectAllTargets(checked) {
            root.querySelectorAll('.target-machine-cb').forEach(cb => cb.checked = checked);
            updateSyncButton();
        }

        // ── Load master device users ──────────────────────────────────────────────────
        async function loadMasterUsers() {
            const masterName = document.getElementById('masterMachine').value;
            if (!masterName) { bsyncAlert('Please select a source machine'); return; }

            const statusEl = document.getElementById('masterLoadStatus');
            const tableWrap = document.getElementById('userTableWrap');
            const statsEl = document.getElementById('userTableStats');

            statusEl.innerHTML = '<div class="loading"><div class="spinner"></div><p>Connecting to source machine and reading users...</p></div>';
            tableWrap.innerHTML = '';
            statsEl.textContent = 'Loading...';

            // Update target list to exclude selected master
            renderTargetMachines(masterName);

            try {
                const msg = await callGet('customize_erpnext.network.biometric.biometric_sync.get_master_device_users', {
                    machine_name: masterName
                });
                if (msg.status !== 'success') throw new Error(msg.message);

                _masterUsers = msg.users;
                _filteredDeviceIds = null; // reset filter
                statusEl.innerHTML = `<div class="alert alert-success">✅ Loaded ${msg.total_on_device} users from ${escapeHtml(masterName)}</div>`;
                renderUserTable(_masterUsers);
            } catch (e) {
                statusEl.innerHTML = `<div class="alert alert-danger">❌ Error: ${escapeHtml(e.message)}</div>`;
                statsEl.textContent = 'Failed to load data';
            }
        }

        // ── Employee filter ───────────────────────────────────────────────────────────
        async function applyEmployeeFilter() {
            const statusEl = document.getElementById('filterStatus');
            const employee = document.getElementById('filterEmpId').value.trim();
            const employee_name = document.getElementById('filterEmpName').value.trim();
            const attendance_device_id = document.getElementById('filterDeviceId').value.trim();
            const date_of_joining = document.getElementById('filterJoinDate').value;

            if (!employee && !employee_name && !attendance_device_id && !date_of_joining) {
                _filteredDeviceIds = null;
                renderUserTable(_masterUsers);
                statusEl.innerHTML = '';
                return;
            }

            statusEl.innerHTML = '<span style="color:#6c757d;">🔍 Filtering...</span>';
            try {
                const msg = await callGet('customize_erpnext.network.biometric.biometric_sync.get_employees_for_sync', {
                    employee, employee_name, attendance_device_id, date_of_joining
                });
                if (msg.status !== 'success') throw new Error(msg.message);
                _filteredDeviceIds = new Set(msg.employees.map(e => String(e.attendance_device_id)).filter(Boolean));
                statusEl.innerHTML = `<span style="color:#1e7e34;">✓ Found ${msg.count} matching employees</span>`;
                renderUserTable(_masterUsers);
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(e.message)}</span>`;
            }
        }

        function clearEmployeeFilter() {
            document.getElementById('filterEmpId').value = '';
            document.getElementById('filterEmpName').value = '';
            document.getElementById('filterDeviceId').value = '';
            document.getElementById('filterJoinDate').value = '';
            document.getElementById('filterStatus').innerHTML = '';
            _filteredDeviceIds = null;
            renderUserTable(_masterUsers);
        }

        // ── Render user table ─────────────────────────────────────────────────────────
        function renderUserTable(users) {
            const wrap = document.getElementById('userTableWrap');
            const statsEl = document.getElementById('userTableStats');

            if (!users || !users.length) {
                wrap.innerHTML = '<div class="no-logs"><p>No users found on source machine</p></div>';
                statsEl.textContent = '0 users';
                updateSyncButton();
                return;
            }

            // Apply device ID filter if active
            let displayUsers = users;
            if (_filteredDeviceIds !== null) {
                displayUsers = users.filter(u => _filteredDeviceIds.has(String(u.user_id)));
            }

            const matched = displayUsers.filter(u => u.matched).length;
            const total = displayUsers.length;
            statsEl.textContent = `Showing ${total} users / ${matched} matched in ERPNext / ${total - matched} unmatched`;

            if (!total) {
                wrap.innerHTML = '<div class="no-logs"><p>No users match the filter criteria</p></div>';
                updateSyncButton();
                return;
            }

            const rows = displayUsers.map(u => {
                const disabled = !u.matched ? 'disabled title="Not found in ERPNext"' : '';
                const checked = u.matched ? 'checked' : '';
                const rowCls = u.matched ? '' : 'unmatched';
                const badge = u.matched
                    ? `<span class="badge-matched">Matched</span>`
                    : `<span class="badge-unmatched">Unmatched</span>`;
                return `
        <tr class="${rowCls}">
            <td><input type="checkbox" class="user-cb" value="${escapeHtml(String(u.user_id))}" ${checked} ${disabled}></td>
            <td>${escapeHtml(String(u.user_id))}</td>
            <td>${escapeHtml(u.employee_name || u.device_name || '—')}</td>
            <td>${escapeHtml(u.employee_id || '—')}</td>
            <td>${escapeHtml(u.date_of_joining || '—')}</td>
            <td>${badge}</td>
        </tr>`;
            }).join('');

            wrap.innerHTML = `
        <div class="user-table-wrap">
            <table>
                <thead>
                    <tr>
                        <th style="width:40px;"><input type="checkbox" id="checkAllUsers" onchange="bsync.selectAllUsers(this.checked)" title="All / None"></th>
                        <th>Device ID</th>
                        <th>Employee Name</th>
                        <th>Employee ID</th>
                        <th>Date of Joining</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;

            root.querySelectorAll('.user-cb').forEach(cb => cb.addEventListener('change', updateSyncButton));
            updateSyncButton();
        }

        function selectAllUsers(checked) {
            root.querySelectorAll('.user-cb:not([disabled])').forEach(cb => cb.checked = checked);
            const allCb = document.getElementById('checkAllUsers');
            if (allCb) allCb.checked = checked;
            updateSyncButton();
        }

        // ── Sync button state ─────────────────────────────────────────────────────────
        function updateSyncButton() {
            const selectedUsers = [...root.querySelectorAll('.user-cb:checked')].length;
            const checkedTargets = [...root.querySelectorAll('.target-machine-cb:checked')].length;
            const syncToErp = document.getElementById('fpSyncToErp')?.checked ?? true;
            const btn = document.getElementById('syncBtn');
            const summary = document.getElementById('syncSummary');
            const hasDestination = checkedTargets > 0 || syncToErp;
            btn.disabled = (selectedUsers === 0 || !hasDestination);
            if (selectedUsers === 0) {
                summary.textContent = 'No users selected';
            } else if (!hasDestination) {
                summary.textContent = 'No destination selected';
            } else {
                const parts = [];
                if (syncToErp) parts.push('ERPNext');
                if (checkedTargets > 0) parts.push(`${checkedTargets} machine${checkedTargets > 1 ? 's' : ''}`);
                summary.textContent = `▶ Sync ${selectedUsers} users → ${parts.join(' + ')}`;
            }
        }

        // ── Helpers ───────────────────────────────────────────────────────────────────
        function setProgressBar(destId, pct, label) {
            const bar = document.getElementById(`mp_bar_${CSS.escape(destId)}`);
            const lbl = document.getElementById(`mp_pct_${CSS.escape(destId)}`);
            if (bar) bar.style.width = Math.min(100, pct) + '%';
            if (lbl) lbl.textContent = label;
        }

        function buildProgressRow(id, label) {
            return `
        <div class="machine-progress" id="mp_${CSS.escape(id)}">
            <div class="machine-progress-label">
                <span>${escapeHtml(label)}</span>
                <span id="mp_pct_${CSS.escape(id)}">⏸ Waiting...</span>
            </div>
            <div class="progress-bar-wrap"><div class="progress-bar" id="mp_bar_${CSS.escape(id)}" style="width:0%"></div></div>
        </div>`;
        }

        // ── Start sync ────────────────────────────────────────────────────────────────
        async function startSync() {
            const masterName = document.getElementById('masterMachine').value;
            const syncToErp = document.getElementById('fpSyncToErp').checked;

            if (!masterName) { bsyncAlert('Please select a source machine'); return; }

            const selectedUserIds = [...root.querySelectorAll('.user-cb:checked')].map(cb => cb.value);
            if (!selectedUserIds.length) { bsyncAlert('No users selected'); return; }

            // Targets: user-selected checkboxes (default = all except source)
            const targetMachines = [...root.querySelectorAll('.target-machine-cb:checked')].map(cb => cb.value);

            if (!syncToErp && targetMachines.length === 0) {
                bsyncAlert('No target machines selected. Check at least one machine or enable "Sync to ERPNext".');
                return;
            }

            // Map device user_ids → ERPNext employee_ids (only matched users)
            const matchedUsers = _masterUsers.filter(u =>
                selectedUserIds.includes(String(u.user_id)) && u.matched && u.employee_id
            );
            const employeeIds = matchedUsers.map(u => u.employee_id);

            // If syncing to ERP: check for existing fingerprints → ask for overwrite
            if (syncToErp && employeeIds.length > 0) {
                try {
                    const checkMsg = await callPost(
                        'customize_erpnext.network.biometric.biometric_sync.check_employees_fingerprints_in_erp',
                        { employee_ids_json: JSON.stringify(employeeIds) }
                    );
                    const existing = checkMsg.existing || {};
                    const existingCount = Object.keys(existing).length;
                    if (existingCount > 0) {
                        const preview = Object.entries(existing).slice(0, 5)
                            .map(([id, cnt]) => {
                                const u = matchedUsers.find(u => u.employee_id === id);
                                return `  ${id} (${u ? u.employee_name || u.device_name || '' : ''}) — ${cnt} fingerprint(s)`;
                            }).join('\n');
                        const more = existingCount > 5 ? `\n  ...and ${existingCount - 5} more` : '';
                        if (!await bsyncConfirm(
                            `${existingCount} employee(s) already have fingerprints in ERPNext:\n${preview}${more}\n\nOverwrite existing data?`
                        )) return;
                    }
                } catch (e) {
                    if (!await bsyncConfirm(`Could not check existing fingerprints: ${e.message}\nContinue anyway?`)) return;
                }
            }

            // Final confirm
            const destParts = [];
            if (syncToErp) destParts.push('ERPNext');
            if (targetMachines.length) destParts.push(`${targetMachines.length} machine(s): ${targetMachines.join(', ')}`);
            if (!await bsyncConfirm(`Sync ${selectedUserIds.length} user(s) from ${masterName}\n→ ${destParts.join('\n→ ')}`)) return;

            const btn = document.getElementById('syncBtn');
            btn.disabled = true;
            btn.textContent = '⏳ Starting...';
            _syncRunningCount++;

            // Build progress section
            const ps = document.getElementById('progressSection');
            ps.classList.add('visible');
            document.getElementById('resultLog').innerHTML = '';
            document.getElementById('progressPhase').textContent = 'Preparing...';

            const progressRows = [];
            if (syncToErp) progressRows.push(buildProgressRow('__erp__', '🗄 ERPNext'));
            targetMachines.forEach(m => progressRows.push(buildProgressRow(m, m)));
            document.getElementById('machineProgressList').innerHTML = progressRows.join('');

            try {
                if (!syncToErp) {
                    // ── Device-to-device only ────────────────────────────────────────────
                    document.getElementById('progressPhase').textContent = 'Phase 1: Device → Devices...';
                    const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.sync_fingerprints', {
                        master_machine_name: masterName,
                        target_machine_names_json: JSON.stringify(targetMachines),
                        user_ids_json: JSON.stringify(selectedUserIds),
                        sync_to_erp: '0',
                    });
                    if (msg.status !== 'success') throw new Error(msg.message);
                    appendResultLog('info-line', `Job ${msg.job_id} submitted — polling...`);
                    await pollSyncJob(msg.job_id, targetMachines, selectedUserIds.length, null);

                } else {
                    // ── Phase 1: Device → ERPNext ────────────────────────────────────────
                    setProgressBar('__erp__', 5, '⏳ Phase 1 running...');
                    document.getElementById('progressPhase').textContent = 'Phase 1: Reading fingerprints from device → ERPNext...';
                    const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.sync_fingerprints', {
                        master_machine_name: masterName,
                        target_machine_names_json: JSON.stringify([]),
                        user_ids_json: JSON.stringify(selectedUserIds),
                        sync_to_erp: '1',
                    });
                    if (msg.status !== 'success') throw new Error(msg.message);
                    appendResultLog('info-line', `Phase 1 job ${msg.job_id} submitted — polling...`);
                    await pollSyncJob(msg.job_id, [], selectedUserIds.length, '__erp__');

                    // ── Phase 2: ERPNext → Devices ───────────────────────────────────────
                    if (targetMachines.length > 0) {
                        document.getElementById('progressPhase').textContent = 'Phase 2: Pushing fingerprints ERPNext → devices...';
                        await runPhase2(employeeIds, matchedUsers, targetMachines);
                    }
                }

                document.getElementById('progressPhase').textContent = '✅ Sync complete';
                appendResultLog('info-line', '\n=== SYNC COMPLETE ===');
            } catch (e) {
                document.getElementById('progressPhase').textContent = '❌ Error: ' + e.message;
                appendResultLog('fail', '❌ ' + e.message);
            } finally {
                btn.textContent = '▶ Sync Fingerprints';
                _syncRunningCount--;
                // recompute disabled state + summary from current selection
                // instead of unconditionally enabling with stale state
                updateSyncButton();
            }
        }

        // ── Shared job-status poller ──────────────────────────────────────────────────
        // Handles server-level errors, jobs that never appear, and an overall timeout,
        // so the UI can never get stuck polling forever. onData(d) runs on each update;
        // resolves with final data on d.status='done', rejects on any failure.
        function pollJobStatus(jobId, onData, opts = {}) {
            const intervalMs = opts.intervalMs || 1500;
            const maxNotFound = opts.maxNotFound || 20;             // ~30s for a job that never appears
            const timeoutMs = opts.timeoutMs || 15 * 60 * 1000;     // hard cap on total polling time
            let notFoundCount = 0;
            const startedAt = Date.now();
            let timer = null;
            const promise = new Promise((resolve, reject) => {
                const stop = (fn, arg) => { clearInterval(timer); timer = null; fn(arg); };
                timer = setInterval(async () => {
                    try {
                        if (Date.now() - startedAt > timeoutMs)
                            return stop(reject, new Error('Timed out waiting for the background job to finish'));
                        const msg = await callGet('customize_erpnext.network.biometric.biometric_sync.get_sync_job_status', { job_id: jobId });
                        if (!msg || msg.status === 'not_found') {
                            if (++notFoundCount >= maxNotFound)
                                return stop(reject, new Error('Job not found or expired — the background worker may be down'));
                            return;
                        }
                        if (msg.status === 'error')
                            return stop(reject, new Error(msg.message || 'Failed to read job status'));
                        notFoundCount = 0;
                        const d = msg.data;
                        if (!d) return;
                        onData(d);
                        if (d.status === 'done') return stop(resolve, d);
                        if (d.status === 'error') return stop(reject, new Error(d.error || 'Job failed'));
                    } catch (e) {
                        // transient network error — keep polling, the timeout is the backstop
                        console.error('Poll error:', e);
                    }
                }, intervalMs);
            });
            promise.cancel = () => { if (timer) { clearInterval(timer); timer = null; } };
            return promise;
        }

        // ── Phase 1 polling (background job) ─────────────────────────────────────────
        function pollSyncJob(jobId, machines, totalUsers, erpDestId) {
            if (_pollTimer && _pollTimer.cancel) _pollTimer.cancel();
            let lastCount = 0;

            _pollTimer = pollJobStatus(jobId, d => {
                const pct = d.progress_pct || 0;
                const doneUsers = d.done_users || 0;

                document.getElementById('progressPhase').textContent = d.phase || '';

                // Update progress bars
                const destIds = erpDestId ? [erpDestId] : machines;
                destIds.forEach(id => {
                    if (d.status === 'done') setProgressBar(id, 100, '✅ Done');
                    else if (d.status === 'running') setProgressBar(id, pct, `${pct}% (${doneUsers}/${totalUsers})`);
                    else setProgressBar(id, pct, '⏸ Queued...');
                });

                // Append new result lines
                (d.results || []).slice(lastCount).forEach(r => {
                    appendResultLog(r.success ? 'ok' : 'fail',
                        `${r.success ? '✓' : '✗'} User ${r.user_id} → ${r.machine}: ${r.message}`);
                });
                lastCount = (d.results || []).length;
            });

            return _pollTimer.then(d => {
                const ok = (d.results || []).filter(r => r.success).length;
                const fail = (d.results || []).length - ok;
                appendResultLog('info-line', `Phase 1 complete: ${ok} OK / ${fail} failed`);
            });
        }

        // ── Phase 2: ERPNext → each device (sequential per machine) ──────────────────
        async function runPhase2(employeeIds, matchedUsers, targetMachines) {
            // Strategy: all machines run in parallel, each machine processes all employees sequentially
            // Same pattern as shared_fingerprint_sync.js (FingerprintSyncManager)
            const machinePromises = targetMachines.map(async (machine) => {
                let ok = 0, fail = 0, done = 0;
                setProgressBar(machine, 2, `0/${employeeIds.length}`);

                for (const empId of employeeIds) {
                    try {
                        const result = await callPost(
                            'customize_erpnext.network.biometric.fingerprint.sync_employee_to_single_machine',
                            { employee_id: empId, machine_name: machine }
                        );
                        if (result && result.success) {
                            appendResultLog('ok', `✓ ${empId} → ${machine}: ${result.message}`);
                            ok++;
                        } else {
                            appendResultLog('fail', `✗ ${empId} → ${machine}: ${result ? result.message : 'No response'}`);
                            fail++;
                        }
                    } catch (e) {
                        appendResultLog('fail', `✗ ${empId} → ${machine}: ${e.message}`);
                        fail++;
                    }
                    done++;
                    setProgressBar(machine, Math.round(done / employeeIds.length * 100), `${done}/${employeeIds.length}`);
                }

                setProgressBar(machine, 100, `✅ ${ok} OK / ${fail} failed`);
                appendResultLog('info-line', `--- ${machine}: ${ok} synced / ${fail} failed ---`);
            });

            await Promise.allSettled(machinePromises);
        }

        function appendResultLog(cls, text) {
            const el = document.getElementById('resultLog');
            const span = document.createElement('div');
            span.className = cls;
            span.textContent = text;
            el.appendChild(span);
            el.scrollTop = el.scrollHeight;
        }

        // ── Wire up checkbox changes ──────────────────────────────────────────────────
        root.addEventListener('change', e => {
            if (e.target.id === 'fpSyncToErp') updateSyncButton();
            if (e.target.classList.contains('target-machine-cb')) updateSyncButton();
            if (e.target.classList.contains('fp41-machine-cb')) fp41UpdateSyncBtn();
        });


        // ════════════════════════════════════════════════════════════════════════════
        // TAB 4.1 — ERP → ATTENDANCE MACHINES
        // ════════════════════════════════════════════════════════════════════════════

        let _fp41Employees = [];   // [{employee_id}]
        let _fp41Syncing = false;

        // ── Guard: warn user if they try to leave while any sync is running ───────────
        // Counter (not boolean): Tab 2 and Tab 3 syncs can overlap; the guard must
        // stay armed until ALL of them finish.
        let _syncRunningCount = 0;
        window.addEventListener('beforeunload', e => {
            if (_syncRunningCount > 0) {
                e.preventDefault();
                e.returnValue = 'A sync is still running. Leaving now will abort it halfway. Are you sure you want to leave?';
            }
        });

        function onFp41ScopeChange() {
            const scope = document.getElementById('fp41Scope').value;
            document.getElementById('fp41DateGroup').style.display = scope === 'date' ? '' : 'none';
            document.getElementById('fp41ManualGroup').style.display = scope === 'manual' ? '' : 'none';
            _fp41Employees = [];
            document.getElementById('fp41EmpStatus').innerHTML = '';
            document.getElementById('fp41EmpTableWrap').style.display = 'none';
            fp41UpdateSyncBtn();
        }

        function fp41RenderEmpTable(employees) {
            const wrap = document.getElementById('fp41EmpTableWrap');
            const tbody = document.getElementById('fp41EmpTableBody');
            if (!employees.length) { wrap.style.display = 'none'; return; }
            tbody.innerHTML = employees.map((e, i) => `
                <tr>
                    <td style="color:#6c757d;">${i + 1}</td>
                    <td><code>${escapeHtml(e.employee_id)}</code></td>
                    <td>${escapeHtml(e.employee_name || '') || '<span class="missing">—</span>'}</td>
                    <td>${escapeHtml(String(e.attendance_device_id ?? '')) || '<span class="missing">—</span>'}</td>
                    <td>${escapeHtml(e.custom_group || '') || '<span class="missing">—</span>'}</td>
                </tr>`).join('');
            wrap.style.display = '';
        }

        async function fp41LoadEmployees() {
            const scope = document.getElementById('fp41Scope').value;
            const statusEl = document.getElementById('fp41EmpStatus');
            statusEl.innerHTML = '<span style="color:#6c757d;">⏳ Loading...</span>';
            _fp41Employees = [];
            document.getElementById('fp41EmpTableWrap').style.display = 'none';
            fp41UpdateSyncBtn();
            try {
                if (scope === 'manual') {
                    const raw = (document.getElementById('fp41ManualIds').value || '').trim();
                    const ids = raw.split('\n').map(s => s.trim()).filter(Boolean);
                    if (!ids.length) { statusEl.innerHTML = '<span style="color:#dc3545;">❌ No Employee IDs entered</span>'; return; }
                    _fp41Employees = ids.map(id => ({ employee_id: id, employee_name: '', attendance_device_id: '', custom_group: '' }));
                    statusEl.innerHTML = `<span style="color:#1e7e34;">✓ ${ids.length} Employee IDs entered</span>`;
                } else {
                    const args = {};
                    if (scope === 'date') {
                        const d = document.getElementById('fp41JoinDate').value;
                        if (d) args.date_of_joining = d;
                    }
                    const msg = await callGet('customize_erpnext.network.biometric.biometric_sync.get_employees_for_sync', args);
                    if (msg.status !== 'success') throw new Error(msg.message);
                    _fp41Employees = msg.employees.map(e => ({
                        employee_id: e.name,
                        employee_name: e.employee_name || '',
                        attendance_device_id: e.attendance_device_id ?? '',
                        custom_group: e.custom_group || '',
                    }));
                    statusEl.innerHTML = `<span style="color:#1e7e34;">✓ Loaded <strong>${msg.count}</strong> active employees</span>`;
                }
                fp41RenderEmpTable(_fp41Employees);
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(e.message)}</span>`;
            }
            fp41UpdateSyncBtn();
        }

        function fp41SelectAllMachines(checked) {
            root.querySelectorAll('.fp41-machine-cb').forEach(cb => cb.checked = checked);
            fp41UpdateSyncBtn();
        }

        function fp41UpdateSyncBtn() {
            const selMachines = [...root.querySelectorAll('.fp41-machine-cb:checked')].length;
            const btn = document.getElementById('fp41SyncBtn');
            const summary = document.getElementById('fp41SyncSummary');
            if (!btn) return;
            btn.disabled = (_fp41Employees.length === 0 || selMachines === 0 || _fp41Syncing);
            if (_fp41Employees.length > 0 && selMachines > 0) {
                const total = _fp41Employees.length * selMachines;
                const selDoors = root.querySelectorAll('.fp41-machine-cb[data-door="1"]:checked').length;
                summary.textContent = `▶ Will sync ${_fp41Employees.length} employees → ${selMachines} machines (${total} operations)`
                    + (selDoors ? ` — incl. 🚪 ${selDoors} door controller(s)` : '');
            } else if (_fp41Employees.length === 0) {
                summary.textContent = 'Load employees first';
            } else {
                summary.textContent = 'No target machines selected';
            }
        }

        function _fp41Scope() {
            const sel = document.getElementById('fp41MachineScope');
            return (sel && sel.value) || 'attendance';
        }

        function fp41MachineScopeChange() {
            fp41RenderMachines();
        }

        function fp41RenderMachines() {
            const wrap = document.getElementById('fp41MachineList');
            if (!wrap) return;
            const hasDoor = _fp41AllMachines.some(m => m.is_door_control);
            document.getElementById('fp41MachineScopeWrap').style.display = hasDoor ? 'inline-flex' : 'none';
            const scope = hasDoor ? _fp41Scope() : 'attendance';
            const list = scope === 'all' ? _fp41AllMachines
                : _fp41AllMachines.filter(m => !!m.is_door_control === (scope === 'door'));
            if (!list.length) {
                wrap.innerHTML = `<div class="alert alert-warning">${scope === 'door' ? 'No door controllers found' : 'No enabled machines found'}</div>`;
                fp41UpdateSyncBtn();
                return;
            }
            wrap.innerHTML = list.map(m => {
                const icon = m.connection_status === 'online' ? '🟢' : '🔴';
                // Door controller: never pre-ticked — a fingerprint there opens the door,
                // so it is ticked on purpose for the few people allowed in.
                const isDoor = !!m.is_door_control;
                const doorBadge = isDoor
                    ? '<span class="badge" style="background:#ede9fe;color:#5b21b6;border:1px solid #ddd6fe;" title="Door controller — a fingerprint here opens the door">🚪 Door</span>'
                    : '';
                return `<label class="machine-item">
                    <input type="checkbox" class="fp41-machine-cb" value="${escapeHtml(m.name)}" data-door="${isDoor ? 1 : 0}"
                        ${m.connection_status === 'online' && !isDoor ? 'checked' : ''}>
                    <span class="machine-item-label">
                        ${icon} <strong>${escapeHtml(m.name)}</strong> — ${escapeHtml(m.device_name || '')}
                        <span style="color:#6c757d;">(${escapeHtml(m.ip_address)})</span>
                    </span>
                    ${doorBadge}
                    ${m.response_time > 0 ? `<span class="badge">${m.response_time}ms</span>` : ''}
                </label>`;
            }).join('');
            fp41UpdateSyncBtn();
        }

        async function fp41StartSync() {
            const selCbs = [...root.querySelectorAll('.fp41-machine-cb:checked')];
            const selMachines = selCbs.map(cb => cb.value);
            if (!_fp41Employees.length || !selMachines.length) return;
            const total = _fp41Employees.length * selMachines.length;
            const doorNames = selCbs.filter(cb => cb.dataset.door === '1').map(cb => cb.value);
            let confirmMsg = `Confirm sync ${_fp41Employees.length} employees → ${selMachines.length} machines?\n(${total} total operations)`;
            if (doorNames.length) {
                confirmMsg += `\n\n🚪 ${doorNames.length} door controller(s) selected: ${doorNames.join(', ')}.`
                    + `\nAll ${_fp41Employees.length} employees will be able to OPEN THE DOOR.`;
            }
            if (!await bsyncConfirm(confirmMsg)) return;

            _fp41Syncing = true;
            _syncRunningCount++;
            fp41UpdateSyncBtn();
            try {

                const ps = document.getElementById('fp41ProgressSection');
                ps.classList.add('visible');
                const logEl = document.getElementById('fp41ResultLog');
                const phaseEl = document.getElementById('fp41ProgressPhase');
                const barEl = document.getElementById('fp41ProgressBar');
                logEl.innerHTML = '';

                function appendLog(cls, text) {
                    const d = document.createElement('div');
                    d.className = cls; d.textContent = text;
                    logEl.appendChild(d); logEl.scrollTop = logEl.scrollHeight;
                }

                appendLog('info-line', `▶ Starting: ${_fp41Employees.length} employees × ${selMachines.length} machines = ${total} operations`);
                appendLog('info-line', `⚡ Strategy: each machine runs in parallel, all employees per machine in sequence`);
                let done = 0, okCount = 0, failCount = 0;

                // Each machine gets its own async worker — all machines run in parallel simultaneously
                // Within each machine: employees processed sequentially (1 connection at a time per machine)
                const machinePromises = selMachines.map(async (machine) => {
                    appendLog('info-line', `── ▶ ${machine} started ──`);
                    let machineOk = 0, machineFail = 0;

                    for (const emp of _fp41Employees) {
                        const empId = emp.employee_id;
                        try {
                            const msg = await callPost('customize_erpnext.network.biometric.fingerprint.sync_employee_to_single_machine', {
                                employee_id: empId,
                                machine_name: machine,
                            });
                            const ok = msg && msg.success !== false && msg.status !== 'error';
                            const detail = msg ? (msg.message || msg.status || 'OK') : 'OK';
                            if (ok) { okCount++; machineOk++; appendLog('ok', `✓ ${empId} → ${machine}: ${detail}`); }
                            else { failCount++; machineFail++; appendLog('fail', `✗ ${empId} → ${machine}: ${detail}`); }
                        } catch (e) {
                            failCount++; machineFail++;
                            appendLog('fail', `✗ ${empId} → ${machine}: ${e.message}`);
                        }
                        done++;
                        barEl.style.width = Math.round(done / total * 100) + '%';
                        phaseEl.textContent = `Syncing... (${done}/${total}) | ✅ ${okCount} ❌ ${failCount}`;
                    }

                    appendLog('info-line', `── ✅ ${machine}: ${machineOk} OK / ${machineFail} failed ──`);
                });

                await Promise.allSettled(machinePromises);

                phaseEl.textContent = `✅ Done: ${okCount} OK / ${failCount} errors`;
                appendLog('info-line', `\n=== COMPLETE: ${okCount} OK / ${failCount} FAILED / ${total} total ===`);

            } finally {
                // always release the flags, or the beforeunload guard stays armed forever
                _fp41Syncing = false;
                _syncRunningCount--;
                fp41UpdateSyncBtn();
            }
        }


        // ════════════════════════════════════════════════════════════════════════════
        // TAB 4.3 — REMOVE LEFT STAFF FROM ATTENDANCE MACHINES
        // ════════════════════════════════════════════════════════════════════════════

        let _del43ScanResult = null;
        let _del43PollTimer = null;

        async function del43Scan() {
            const delayDays = parseInt(document.getElementById('del43DelayDays').value) || 45;
            const inclUnmatched = document.getElementById('del43IncludeUnmatched').checked ? 1 : 0;
            const btn = document.getElementById('del43ScanBtn');
            const statusEl = document.getElementById('del43ScanStatus');

            btn.disabled = true; btn.textContent = '⏳ Scanning...';
            statusEl.textContent = 'Connecting and scanning all attendance machines...';
            document.getElementById('del43PreviewSection').style.display = 'none';
            document.getElementById('del43ProgressSection').classList.remove('visible');

            try {
                const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.get_left_employees_on_machines', {
                    delay_days: delayDays, include_unmatched: inclUnmatched,
                });
                if (msg.status !== 'success') throw new Error(msg.message);
                _del43ScanResult = msg;
                statusEl.textContent = '';
                del43RenderPreview(msg);
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(e.message)}</span>`;
            }
            btn.disabled = false; btn.textContent = '🔍 Scan All Machines';
        }

        function del43RenderPreview(result) {
            const users = result.users_to_delete || [];
            const machines = result.machines_scanned || [];

            // Machines summary
            const mHtml = machines.map(m => {
                const icon = m.success ? '✅' : '❌';
                const info = m.success ? `${m.total_users} users` : escapeHtml(m.error || 'Error');
                return `<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 6px 2px 0;
                    font-size:12px;padding:2px 8px;background:#f0f0f0;border-radius:4px;">
                    ${icon} <strong>${escapeHtml(m.machine)}</strong> (${info})
                </span>`;
            }).join('');

            document.getElementById('del43ScanSummary').innerHTML = `
                <div style="margin-bottom:10px;">
                    <div style="font-size:12px;color:#6c757d;margin-bottom:6px;">Scanned machines:</div>
                    <div style="flex-wrap:wrap;display:flex;">${mHtml}</div>
                </div>
                <div style="font-size:13px;color:#6c757d;margin-bottom:4px;">
                    Today: <strong>${escapeHtml(result.today)}</strong> &nbsp;|&nbsp;
                    Threshold: <strong>${result.delay_days} days</strong> &nbsp;|&nbsp;
                    Total user IDs on devices: <strong>${result.total_unique_user_ids}</strong> &nbsp;|&nbsp;
                    To keep: <strong>${result.users_to_keep_count}</strong>
                </div>`;

            const tableEl = document.getElementById('del43PreviewTable');
            const delBtn = document.getElementById('del43DeleteBtn');

            if (!users.length) {
                tableEl.innerHTML = '<div class="alert alert-success">✅ No users need to be deleted with the current settings.</div>';
                delBtn.style.display = 'none';
            } else {
                const leftCount = users.filter(u => u.reason_type === 'left_employee').length;
                const unmatchedCount = users.filter(u => u.reason_type === 'unmatched').length;

                const rows = users.map((u, idx) => {
                    const empCell = u.employee_id
                        ? `<strong>${escapeHtml(u.employee_name || '')}</strong><br><small>${escapeHtml(u.employee_id)}</small>`
                        : `<em style="color:#6c757d;">— not found in ERPNext</em>`;
                    const rdCell = u.relieving_date
                        ? `${escapeHtml(u.relieving_date)}<br><small style="color:#dc3545;">(+${u.days_since_relieving}d)</small>`
                        : '—';
                    const macTags = (u.machines || []).map(m =>
                        `<span style="font-size:11px;padding:1px 5px;background:#e9ecef;border-radius:3px;margin:1px;">${escapeHtml(m)}</span>`
                    ).join('');
                    return `<tr>
                        <td style="text-align:center;padding:6px 4px;">
                            <input type="checkbox" class="del43-user-chk" data-idx="${idx}" checked style="width:14px;height:14px;">
                        </td>
                        <td style="padding:6px 8px;"><strong>${escapeHtml(String(u.user_id))}</strong></td>
                        <td style="padding:6px 8px;">${empCell}</td>
                        <td style="padding:6px 8px;font-size:12px;">${escapeHtml(u.reason)}</td>
                        <td style="padding:6px 8px;font-size:12px;white-space:nowrap;">${rdCell}</td>
                        <td style="padding:6px 8px;">${macTags}</td>
                    </tr>`;
                }).join('');

                tableEl.innerHTML = `
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <div>
                            <span style="background:#dc3545;color:white;padding:2px 8px;border-radius:10px;font-size:12px;">${users.length} users to delete</span>
                            ${leftCount ? `<span style="background:#ffc107;color:#212529;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:4px;">${leftCount} resigned</span>` : ''}
                            ${unmatchedCount ? `<span style="background:#6c757d;color:white;padding:2px 8px;border-radius:10px;font-size:11px;margin-left:4px;">${unmatchedCount} unmatched</span>` : ''}
                        </div>
                        <div style="font-size:12px;">
                            <a href="#" onclick="bsync.del43SelectAll(true);return false;" style="margin-right:8px;">All</a>
                            <a href="#" onclick="bsync.del43SelectAll(false);return false;">None</a>
                        </div>
                    </div>
                    <div class="del-preview-wrap">
                        <table>
                            <thead><tr>
                                <th style="width:36px;"></th>
                                <th>User ID</th><th>Employee</th><th>Reason</th><th>Relieving Date</th><th>Machine</th>
                            </tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                    <div class="alert alert-info" style="margin-top:12px;font-size:13px;">
                        🔒 Fingerprint data in ERPNext <strong>will not be deleted</strong> — it can be re-synced at any time.
                    </div>`;
                delBtn.style.display = '';
            }
            document.getElementById('del43PreviewSection').style.display = '';
        }

        function del43SelectAll(checked) {
            root.querySelectorAll('.del43-user-chk').forEach(cb => cb.checked = checked);
        }

        function del43ResetPreview() {
            document.getElementById('del43PreviewSection').style.display = 'none';
            _del43ScanResult = null;
        }

        async function del43Delete() {
            if (!_del43ScanResult) return;
            const allUsers = _del43ScanResult.users_to_delete || [];
            const checkedIdxs = [];
            root.querySelectorAll('.del43-user-chk:checked').forEach(cb => checkedIdxs.push(parseInt(cb.dataset.idx)));
            if (!checkedIdxs.length) { bsyncAlert('No users selected'); return; }

            const selected = checkedIdxs.map(i => allUsers[i]);
            if (!await bsyncConfirm(`Confirm deletion of ${selected.length} user(s) from attendance machines?\nThis action CANNOT be undone.`)) return;

            const deleteBtn = document.getElementById('del43DeleteBtn');
            del43RunDeleteJob(selected, deleteBtn, '🗑 Delete Selected Users', () => {
                _del43ScanResult = null;
                document.getElementById('del43PreviewSection').style.display = 'none';
            });
        }

        // Shared submit + poll for both bulk and specific-employee deletion.
        async function del43RunDeleteJob(selected, btn, defaultLabel, onDone) {
            btn.disabled = true; btn.textContent = '⏳ Submitting job...';

            const ps = document.getElementById('del43ProgressSection');
            ps.classList.add('visible');
            const logEl = document.getElementById('del43ResultLog');
            const phaseEl = document.getElementById('del43ProgressPhase');
            const barEl = document.getElementById('del43ProgressBar');
            logEl.innerHTML = '';
            barEl.style.width = '0%';

            function appendLog(cls, text) {
                const d = document.createElement('div'); d.className = cls; d.textContent = text;
                logEl.appendChild(d); logEl.scrollTop = logEl.scrollHeight;
            }

            try {
                const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.delete_users_from_machines', {
                    users_json: JSON.stringify(selected),
                });
                if (msg.status !== 'success') throw new Error(msg.message);

                const jobId = msg.job_id;
                appendLog('info-line', `Job ${jobId} submitted — waiting for worker...`);
                btn.textContent = '⏳ Deleting...';

                if (_del43PollTimer && _del43PollTimer.cancel) _del43PollTimer.cancel();
                let lastCount = 0;
                _del43PollTimer = pollJobStatus(jobId, d => {
                    phaseEl.textContent = d.phase || '';
                    barEl.style.width = (d.progress_pct || 0) + '%';

                    (d.results || []).slice(lastCount).forEach(r => {
                        appendLog(r.success ? 'ok' : 'fail',
                            `${r.success ? '✓' : '✗'} User ${r.user_id} ← ${r.machine}: ${r.message}`);
                    });
                    lastCount = (d.results || []).length;
                });

                const d = await _del43PollTimer;
                btn.disabled = false; btn.textContent = defaultLabel;
                const ok = (d.results || []).filter(r => r.success).length;
                const fail = (d.results || []).length - ok;
                appendLog('info-line', `\n=== DONE: ${ok} OK / ${fail} FAILED ===`);
                if (onDone) onDone();
            } catch (e) {
                appendLog('fail', '❌ ' + e.message);
                btn.disabled = false; btn.textContent = defaultLabel;
            }
        }

        // ── Tab 4 — Delete a specific employee (targeted) ───────────────────
        let _del43FindResult = null;

        async function del43FindEmp() {
            const query = document.getElementById('del43FindInput').value.trim();
            const btn = document.getElementById('del43FindBtn');
            const statusEl = document.getElementById('del43FindStatus');
            const resultEl = document.getElementById('del43FindResult');
            _del43FindResult = null;
            resultEl.style.display = 'none';
            if (!query) { statusEl.textContent = 'Please enter an Employee ID, Device ID or name'; return; }

            btn.disabled = true; btn.textContent = '⏳ Finding...';
            statusEl.textContent = 'Searching employee and scanning machines...';
            try {
                const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.find_employee_on_machines', { query });
                statusEl.textContent = '';
                del43RenderFind(msg);
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(e.message)}</span>`;
            }
            btn.disabled = false; btn.textContent = '🔍 Find';
        }

        function del43RenderFind(msg) {
            const resultEl = document.getElementById('del43FindResult');
            resultEl.style.display = '';

            if (msg.status === 'error') {
                resultEl.innerHTML = `<div class="alert alert-warning">⚠ ${escapeHtml(msg.message || 'Not found')}</div>`;
                return;
            }

            if (msg.status === 'multiple') {
                // data-attribute + listener instead of inline onclick: dataset returns the
                // HTML-decoded raw value, so IDs with quotes can't break the handler
                const rows = (msg.candidates || []).map(c =>
                    `<tr style="cursor:pointer;" class="del43-candidate" data-emp-id="${escapeHtml(c.employee_id)}">
                        <td style="padding:6px 8px;"><strong>${escapeHtml(c.employee_id)}</strong></td>
                        <td style="padding:6px 8px;">${escapeHtml(c.employee_name || '')}</td>
                        <td style="padding:6px 8px;">${escapeHtml(c.attendance_device_id || '—')}</td>
                        <td style="padding:6px 8px;">${escapeHtml(c.status || '')}</td>
                    </tr>`).join('');
                resultEl.innerHTML = `
                    <div style="font-size:13px;margin-bottom:6px;">Multiple matches — pick one:</div>
                    <div class="del-preview-wrap"><table>
                        <thead><tr><th>Employee ID</th><th>Name</th><th>Device ID</th><th>Status</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table></div>`;
                resultEl.querySelectorAll('.del43-candidate').forEach(tr =>
                    tr.addEventListener('click', () => del43PickCandidate(tr.dataset.empId)));
                return;
            }

            const emp = msg.employee || {};
            const empCard = `
                <div style="font-size:13px;margin-bottom:10px;">
                    <strong>${escapeHtml(emp.employee_name || '')}</strong>
                    <small>(${escapeHtml(emp.employee_id || '')})</small> &nbsp;|&nbsp;
                    Device ID: <strong>${escapeHtml(emp.attendance_device_id || '—')}</strong> &nbsp;|&nbsp;
                    Status: <strong>${escapeHtml(emp.status || '')}</strong>
                    ${emp.relieving_date ? ` &nbsp;|&nbsp; Relieved: ${escapeHtml(emp.relieving_date)}` : ''}
                </div>`;

            if (msg.status === 'blocked') {
                resultEl.innerHTML = empCard +
                    `<div class="alert alert-warning">🔒 ${escapeHtml(msg.message)}</div>`;
                return;
            }

            // status === 'success'
            _del43FindResult = msg;
            const found = msg.found_on || [];
            if (!found.length) {
                resultEl.innerHTML = empCard +
                    `<div class="alert alert-success">✅ This user_id was not found on any device — nothing to delete.</div>`;
                return;
            }

            const machineRows = found.map((f, idx) =>
                `<tr>
                    <td style="text-align:center;padding:6px 4px;">
                        <input type="checkbox" class="del43-find-chk" data-idx="${idx}" checked style="width:14px;height:14px;">
                    </td>
                    <td style="padding:6px 8px;"><strong>${escapeHtml(f.machine)}</strong>
                        ${f.device_name ? `<br><small>${escapeHtml(f.device_name)}</small>` : ''}</td>
                    <td style="padding:6px 8px;">${escapeHtml(f.on_device_name || '')}</td>
                </tr>`).join('');

            resultEl.innerHTML = empCard + `
                <div style="font-size:13px;color:#6c757d;margin-bottom:6px;">
                    Found on <strong>${found.length}</strong> device(s):
                </div>
                <div class="del-preview-wrap"><table>
                    <thead><tr><th style="width:36px;"></th><th>Machine</th><th>Name on device</th></tr></thead>
                    <tbody>${machineRows}</tbody>
                </table></div>
                <div class="alert alert-info" style="margin-top:12px;font-size:13px;">
                    🔒 Fingerprint data in ERPNext <strong>will not be deleted</strong>.
                </div>
                <div style="margin-top:14px;">
                    <button class="btn btn-danger" id="del43FindDeleteBtn" onclick="bsync.del43SpecificDelete()">🗑 Delete from selected devices</button>
                </div>`;
        }

        function del43PickCandidate(empId) {
            document.getElementById('del43FindInput').value = empId;
            del43FindEmp();
        }

        async function del43SpecificDelete() {
            if (!_del43FindResult) return;
            const emp = _del43FindResult.employee || {};
            const found = _del43FindResult.found_on || [];
            const machines = [];
            root.querySelectorAll('.del43-find-chk:checked').forEach(cb => {
                const f = found[parseInt(cb.dataset.idx)];
                if (f) machines.push(f.machine);
            });
            if (!machines.length) { bsyncAlert('No devices selected'); return; }

            if (!await bsyncConfirm(`Delete user_id ${emp.attendance_device_id} (${emp.employee_name}) from ${machines.length} device(s)?\nThis action CANNOT be undone.`)) return;

            const selected = [{
                user_id: emp.attendance_device_id,
                employee_id: emp.employee_id,
                employee_name: emp.employee_name,
                machines: machines,
            }];
            const btn = document.getElementById('del43FindDeleteBtn');
            del43RunDeleteJob(selected, btn, '🗑 Delete from selected devices', () => {
                _del43FindResult = null;
                document.getElementById('del43FindResult').style.display = 'none';
            });
        }


        // ════════════════════════════════════════════════════════════════════════════
        // TAB MACHINES MANAGEMENT
        // ════════════════════════════════════════════════════════════════════════════

        let _machinesList = [];
        let _machinesLoaded = false;
        // attendance | door | all — door / all only for the Door Control role (server-checked)
        let _machinesScope = 'attendance';

        function _machinesStatusText() {
            const kind = { attendance: 'attendance ', door: 'door control ', all: '' }[_machinesScope] || '';
            return `${_machinesList.length} ${kind}machines`;
        }

        async function loadMachineCards() {
            _machinesLoaded = true;
            const gridEl = document.getElementById('machineCardsGrid');
            const loadingEl = document.getElementById('machinesLoadingArea');
            const statusEl = document.getElementById('machinesGlobalStatus');

            // an earlier failure replaced the spinner with the error
            loadingEl.innerHTML = '<div class="spinner"></div><p style="margin-top:8px;">Loading machines...</p>';
            loadingEl.style.display = 'block';
            gridEl.style.display = 'none';
            statusEl.textContent = '';

            try {
                const msg = await callGet('customize_erpnext.network.biometric.biometric_sync.get_attendance_machines', { scope: _machinesScope });
                if (msg.status !== 'success') throw new Error(msg.message || 'Failed to load machine list');
                document.getElementById('machinesScopeWrap').style.display = msg.can_door ? 'inline-flex' : 'none';
                _machinesList = msg.machines || [];
                renderMachineCards();
                loadingEl.style.display = 'none';
                gridEl.style.display = '';
                statusEl.textContent = `${_machinesStatusText()}`;
            } catch (e) {
                loadingEl.innerHTML = `<div class="alert alert-danger">❌ ${escapeHtml(e.message)}</div>`;
            }
        }

        function machinesRefresh() {
            _machinesLoaded = false;
            loadMachineCards();
        }

        function machinesScopeChange() {
            _machinesScope = document.getElementById('machinesScope').value;
            // info table + user lists belong to the previous set of machines
            Object.keys(_muData).forEach(k => delete _muData[k]);
            document.getElementById('allMachinesInfoSection').style.display = 'none';
            document.getElementById('machineUsersSection').style.display = 'none';
            machinesRefresh();
        }

        function renderMachineCards() {
            const gridEl = document.getElementById('machineCardsGrid');
            if (!_machinesList.length) {
                gridEl.innerHTML = '<div class="alert alert-info">No enabled machines of this kind in Attendance Machine Setting.</div>';
                return;
            }
            gridEl.innerHTML = _machinesList.map(m => {
                const doorBadge = m.is_door_control
                    ? '<span style="font-size:11px;background:#ede9fe;color:#5b21b6;padding:1px 8px;border-radius:10px;margin-left:6px;border:1px solid #ddd6fe;">🚪 Door</span>'
                    : '';
                return `
                <div class="machine-card" id="mc_${CSS.escape(m.name)}">
                    <div class="machine-card-head">
                        <div class="machine-card-name">
                            ${m.is_door_control ? '🚪' : '🖥'} ${escapeHtml(m.name)}${doorBadge}
                        </div>
                    </div>
                    <div class="machine-card-meta">📌 ${escapeHtml(m.device_name || '')}${m.model ? ' · ' + escapeHtml(m.model) : ''}</div>
                    <div class="machine-card-meta">📡 ${escapeHtml(m.ip_address)}:${m.port || 4370}</div>
                    ${m.location ? `<div class="machine-card-meta">📍 ${escapeHtml(m.location)}</div>` : ''}
                    <div class="machine-card-actions">
                        <button class="btn btn-sm btn-info-sm machine-action" data-action="info" data-machine="${escapeHtml(m.name)}">ℹ Info</button>
                        <button class="btn btn-sm btn-warn-sm machine-action" data-action="time" data-machine="${escapeHtml(m.name)}">🕐 Sync Time</button>
                        <button class="btn btn-sm btn-danger-sm machine-action" data-action="reboot" data-machine="${escapeHtml(m.name)}">🔁 Reboot</button>
                        <button class="btn btn-sm btn-success machine-action" data-action="users" data-machine="${escapeHtml(m.name)}">👥 Users</button>
                    </div>
                    <div class="machine-info-panel" id="mip_${CSS.escape(m.name)}">
                        <span style="color:var(--text-3);font-size:12px;">Click <em>Info</em> to read device information...</span>
                    </div>
                </div>`;
            }).join('');
            // data-attribute + listeners instead of inline onclick with interpolated names
            const actions = { info: machineGetInfo, time: machineSyncTime, reboot: machineReboot, users: machineShowUsers };
            gridEl.querySelectorAll('.machine-action').forEach(btn =>
                btn.addEventListener('click', () => actions[btn.dataset.action](btn.dataset.machine)));
        }

        async function machineGetInfo(machineName) {
            const panelEl = document.getElementById(`mip_${CSS.escape(machineName)}`);
            if (!panelEl) return;
            panelEl.classList.add('visible');
            panelEl.innerHTML = '<div style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:18px;height:18px;border-width:2px;"></div> Connecting...</div>';

            try {
                const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.machine_get_info', { machine_name: machineName });
                if (msg.status !== 'success') throw new Error(msg.message);

                function capBar(used, cap) {
                    if (!cap) return '';
                    const pct = Math.min(100, Math.round(used / cap * 100));
                    const color = pct > 85 ? '#dc3545' : pct > 60 ? '#ffc107' : '#28a745';
                    return `<span class="cap-bar-wrap"><span class="cap-bar-inner" style="width:${pct}%;background:${color};"></span></span>`;
                }

                const items = [
                    { label: 'Firmware', value: msg.firmware_version || '—' },
                    { label: 'Serial #', value: msg.serial_number || '—' },
                    { label: 'Platform', value: msg.platform || '—' },
                    { label: 'FP Version', value: msg.fp_version || '—' },
                    { label: 'Device Name', value: msg.device_name || '—' },
                    { label: 'MAC Address', value: msg.mac_address || '—' },
                    {
                        label: 'Users',
                        value: `${msg.user_count} / ${msg.user_capacity || '?'}`,
                        extra: capBar(msg.user_count, msg.user_capacity),
                    },
                    {
                        label: 'Fingerprints',
                        value: `${msg.fp_count} / ${msg.fp_capacity || '?'}`,
                        extra: capBar(msg.fp_count, msg.fp_capacity),
                    },
                    {
                        label: 'Attendance Records',
                        value: `${msg.record_count} / ${msg.record_capacity || '?'}`,
                        extra: capBar(msg.record_count, msg.record_capacity),
                    },
                    { label: 'Face', value: msg.face_count > 0 ? `${msg.face_count} / ${msg.face_capacity || '?'}` : '—' },
                    { label: 'Device Time', value: msg.device_time || '—' },
                    { label: 'Model (ERP)', value: msg.model || '—' },
                ];

                panelEl.innerHTML = `
                    <div style="font-weight:600;font-size:12px;margin-bottom:10px;color:var(--text-2);">📊 Device Info</div>
                    <div class="info-grid">
                        ${items.map(it => `
                        <div class="info-item">
                            <span class="ilabel">${escapeHtml(it.label)}</span>
                            <span class="ivalue">${escapeHtml(String(it.value))}${it.extra || ''}</span>
                        </div>`).join('')}
                    </div>
                    <div style="margin-top:8px;font-size:11px;color:var(--text-3);">
                        Updated at: ${new Date().toLocaleTimeString('en-US')}
                        &nbsp;·&nbsp; <a href="#" class="mip-refresh" style="font-size:11px;">Refresh</a>
                    </div>`;
                panelEl.querySelector('.mip-refresh').addEventListener('click', ev => {
                    ev.preventDefault();
                    machineGetInfo(machineName);
                });
            } catch (e) {
                panelEl.innerHTML = `<span style="color:#dc3545;font-size:12px;">❌ ${escapeHtml(e.message)}</span>`;
            }
        }

        async function machineSyncTime(machineName) {
            const statusEl = document.getElementById('machinesGlobalStatus');
            statusEl.textContent = `⏳ Syncing time on ${machineName}...`;
            try {
                const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.machine_sync_time', { machine_name: machineName });
                if (msg.status !== 'success') throw new Error(msg.message);
                statusEl.textContent = `✅ ${machineName}: Time synced | Server: ${msg.server_time} | Device: ${msg.device_time} | Drift: ${msg.drift_seconds}s`;
                setTimeout(() => { statusEl.textContent = `${_machinesStatusText()}`; }, 6000);
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(machineName)}: ${escapeHtml(e.message)}</span>`;
            }
        }

        async function machineReboot(machineName) {
            if (!await bsyncConfirm(`Reboot machine "${machineName}"?\nThe device will restart and disconnect for a few seconds.`)) return;
            const statusEl = document.getElementById('machinesGlobalStatus');
            statusEl.textContent = `⏳ Sending reboot command to ${machineName}...`;
            try {
                const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.machine_reboot', { machine_name: machineName });
                if (msg.status !== 'success') throw new Error(msg.message);
                statusEl.textContent = `✅ ${machineName}: Reboot command sent`;
                setTimeout(() => { statusEl.textContent = `${_machinesStatusText()}`; }, 5000);
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(machineName)}: ${escapeHtml(e.message)}</span>`;
            }
        }

        async function machinesSyncTimeAll() {
            if (!_machinesList.length) { bsyncAlert('Machines not loaded'); return; }
            if (!await bsyncConfirm(`Sync time for ALL ${_machinesList.length} machines?`)) return;
            const statusEl = document.getElementById('machinesGlobalStatus');
            statusEl.textContent = `⏳ Syncing time on ${_machinesList.length} machines (parallel)...`;

            const results = await Promise.allSettled(
                _machinesList.map(m => callPost('customize_erpnext.network.biometric.biometric_sync.machine_sync_time', { machine_name: m.name }))
            );
            const ok = results.filter(r => r.status === 'fulfilled' && r.value && r.value.status === 'success').length;
            const fail = results.length - ok;
            statusEl.textContent = `✅ Time sync done: ${ok} OK / ${fail} failed`;
            setTimeout(() => { statusEl.textContent = `${_machinesStatusText()}`; }, 6000);
        }

        async function machinesRebootAll() {
            if (!_machinesList.length) { bsyncAlert('Machines not loaded'); return; }
            if (!await bsyncConfirm(`⚠ REBOOT ALL ${_machinesList.length} machines?\n\nAll devices will restart — this affects employees currently clocking in!`)) return;

            const statusEl = document.getElementById('machinesGlobalStatus');
            let done = 0;
            for (const m of _machinesList) {
                statusEl.textContent = `⏳ Reboot ${m.name}... (${done + 1}/${_machinesList.length})`;
                try {
                    await callPost('customize_erpnext.network.biometric.biometric_sync.machine_reboot', { machine_name: m.name });
                } catch (e) {
                    console.error(`Reboot ${m.name}:`, e.message);
                }
                done++;
                await new Promise(r => setTimeout(r, 800));
            }
            statusEl.textContent = `✅ Reboot command sent to ${done} machines`;
            setTimeout(() => { statusEl.textContent = `${_machinesStatusText()}`; }, 6000);
        }

        async function machinesLoadAllInfo() {
            if (!_machinesList.length) { bsyncAlert('Machines not loaded'); return; }

            const statusEl = document.getElementById('machinesGlobalStatus');
            const section = document.getElementById('allMachinesInfoSection');
            const tbody = document.getElementById('allMachinesInfoBody');
            const tsEl = document.getElementById('allInfoTimestamp');

            section.style.display = '';

            // Pre-fill rows with loading state
            tbody.innerHTML = _machinesList.map(m => `
                <tr class="row-loading" id="ait_${CSS.escape(m.name)}">
                    <td><strong>${escapeHtml(m.name)}</strong></td>
                    <td>${escapeHtml(m.ip_address)}:${m.port || 4370}</td>
                    <td colspan="9"><div style="display:flex;align-items:center;gap:8px;"><div class="spinner" style="width:14px;height:14px;border-width:2px;"></div> Connecting...</div></td>
                </tr>`).join('');

            section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            statusEl.textContent = `⏳ Reading info from ${_machinesList.length} machines (parallel)...`;

            function capCell(used, cap) {
                if (!cap) return escapeHtml(String(used));
                const pct = Math.min(100, Math.round(used / cap * 100));
                const color = pct > 85 ? '#dc3545' : pct > 60 ? '#f0ad4e' : '#28a745';
                // bar keeps the bright fill; the % label needs darker shades to stay readable on white
                const textColor = pct > 85 ? '#dc3545' : pct > 60 ? '#b45309' : '#1e7e34';
                return `<div class="ai-cap">
                    <span>${used} / ${cap}</span>
                    <div class="ai-cap-bar"><div class="ai-cap-fill" style="width:${pct}%;background:${color};"></div></div>
                    <span style="color:${textColor};font-weight:600;">${pct}%</span>
                </div>`;
            }

            const tasks = _machinesList.map(async m => {
                const tr = document.getElementById(`ait_${CSS.escape(m.name)}`);
                try {
                    const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.machine_get_info', { machine_name: m.name });
                    if (!tr) return;
                    if (msg.status !== 'success') throw new Error(msg.message || 'Error');
                    tr.className = '';
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(m.name)}</strong></td>
                        <td style="font-family:monospace;">${escapeHtml(msg.ip_address || m.ip_address)}:${msg.port || m.port || 4370}</td>
                        <td>${escapeHtml(msg.firmware_version || '—')}</td>
                        <td style="font-family:monospace;">${escapeHtml(msg.serial_number || '—')}</td>
                        <td>${escapeHtml(msg.platform || '—')}</td>
                        <td>${escapeHtml(msg.fp_version || '—')}</td>
                        <td>${capCell(msg.user_count, msg.user_capacity)}</td>
                        <td>${capCell(msg.fp_count, msg.fp_capacity)}</td>
                        <td>${capCell(msg.record_count, msg.record_capacity)}</td>
                        <td style="font-family:monospace;white-space:nowrap;">${escapeHtml(msg.device_time || '—')}</td>
                        <td><span style="color:#1e7e34;">✅ OK</span></td>`;
                } catch (e) {
                    if (!tr) return;
                    tr.className = 'row-error';
                    tr.innerHTML = `
                        <td><strong>${escapeHtml(m.name)}</strong></td>
                        <td>${escapeHtml(m.ip_address)}:${m.port || 4370}</td>
                        <td colspan="9">❌ ${escapeHtml(e.message)}</td>`;
                }
            });

            await Promise.allSettled(tasks);

            const ok = tbody.querySelectorAll('tr:not(.row-error):not(.row-loading)').length;
            const fail = tbody.querySelectorAll('tr.row-error').length;
            tsEl.textContent = `Updated: ${new Date().toLocaleTimeString('en-US')}`;
            statusEl.textContent = `📊 Info: ${ok} OK / ${fail} failed`;
            setTimeout(() => { statusEl.textContent = `${_machinesStatusText()}`; }, 8000);
        }

        // ── Users on machines (view + xlsx) ─────────────────────────────────────────
        // machine name -> { read_at, loaded_at, users } — successful reads only
        const _muData = {};
        const MU_ALL = '__all__';
        // the server keeps each list 30 min for the xlsx; older ones are re-read first
        const MU_MAX_AGE_MS = 25 * 60 * 1000;

        async function _muLoad(machineName) {
            try {
                const msg = await callPost('customize_erpnext.network.biometric.biometric_sync.machine_get_users', { machine_name: machineName });
                if (msg.status !== 'success') throw new Error(msg.message || 'Failed to read users');
                _muData[machineName] = { read_at: msg.read_at, loaded_at: Date.now(), users: msg.users || [],
                                     is_door_control: !!msg.is_door_control };
            } catch (e) {
                // a failed re-read must not leave the old list in the combined view
                delete _muData[machineName];
                throw e;
            }
        }

        // user_ids ticked in the current view (cleared when the view changes)
        const _muSelected = new Set();
        const MU_PROTECTED = 'Employee still working — never deleted from attendance machines';

        // 🔴 attendance machine: never delete a working employee (server enforces it too);
        // door controller: anyone (its list is the few people allowed to open the door)
        function _muCanDelete(u, machineName) {
            return !!(_muData[machineName] && (_muData[machineName].is_door_control || !u.is_working));
        }

        // machines the row would be deleted from in the current view
        function _muDeleteTargets(u, selected) {
            return (selected === MU_ALL ? u.machines : [selected]).filter(m => _muCanDelete(u, m));
        }

        function _muUpdateSelUi() {
            const btn = document.getElementById('muDeleteBtn');
            if (btn.dataset.busy) return;
            btn.disabled = !_muSelected.size;
            btn.textContent = _muSelected.size ? `🗑 Delete selected (${_muSelected.size})` : '🗑 Delete selected';
            const all = document.getElementById('muSelAll');
            if (all) {
                const boxes = [...document.querySelectorAll('#muBody .mu-sel:not(:disabled)')];
                all.checked = boxes.length > 0 && boxes.every(b => b.checked);
            }
        }

        function muMachineChange() {
            _muSelected.clear();
            muRender();
        }

        document.getElementById('muBody').addEventListener('change', ev => {
            const box = ev.target.closest('.mu-sel');
            if (!box) return;
            if (box.checked) _muSelected.add(box.dataset.uid); else _muSelected.delete(box.dataset.uid);
            _muUpdateSelUi();
        });

        function _muLoadedNames() {
            return _machinesList.map(m => m.name).filter(n => _muData[n]);
        }

        // after a failed read dropped a list: redraw the open view (or hide it if nothing is left)
        function _muRefreshView() {
            const section = document.getElementById('machineUsersSection');
            if (section.style.display === 'none') return;
            const names = _muLoadedNames();
            if (!names.length) { section.style.display = 'none'; return; }
            const cur = document.getElementById('muMachine').value;
            _muShow(cur === MU_ALL || _muData[cur] ? cur : (names.length > 1 ? MU_ALL : names[0]));
        }

        function _muUidCmp(a, b) {
            const na = /^\d+$/.test(a), nb = /^\d+$/.test(b);
            if (na && nb) return Number(a) - Number(b);
            if (na !== nb) return na ? -1 : 1;
            return a.localeCompare(b);
        }

        async function machineShowUsers(machineName) {
            const statusEl = document.getElementById('machinesGlobalStatus');
            statusEl.textContent = `⏳ Reading users from ${machineName}...`;
            try {
                await _muLoad(machineName);
                statusEl.textContent = `✅ ${machineName}: ${_muData[machineName].users.length} users`;
                _muShow(machineName);
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(machineName)}: ${escapeHtml(e.message)}</span>`;
                _muRefreshView();
            }
        }

        async function machinesLoadUsersAll() {
            if (!_machinesList.length) { bsyncAlert('Machines not loaded'); return; }
            const statusEl = document.getElementById('machinesGlobalStatus');
            const list = _machinesList.slice();
            statusEl.textContent = `⏳ Reading users from ${list.length} machines (parallel)...`;
            const results = await Promise.allSettled(list.map(m => _muLoad(m.name)));
            const failed = results
                .map((r, i) => r.status === 'rejected' ? `${list[i].name}: ${r.reason && r.reason.message}` : null)
                .filter(Boolean);
            statusEl.textContent = `👥 Users: ${list.length - failed.length} OK / ${failed.length} failed`;
            if (failed.length) bsyncAlert('Could not read users from:\n' + failed.join('\n'));
            if (_muLoadedNames().length) _muShow(MU_ALL);
            else _muRefreshView();
        }

        function _muShow(selected) {
            const names = _muLoadedNames();
            const sel = document.getElementById('muMachine');
            const opts = names.length > 1 ? [`<option value="${MU_ALL}">All loaded machines (${names.length})</option>`] : [];
            names.forEach(n => opts.push(`<option value="${escapeHtml(n)}">${escapeHtml(n)} (${_muData[n].users.length})</option>`));
            sel.innerHTML = opts.join('');
            sel.value = (selected === MU_ALL && names.length < 2) ? (names[0] || '') : selected;
            _muSelected.clear();
            const section = document.getElementById('machineUsersSection');
            section.style.display = '';
            muRender();
            section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        // one row per user_id across the loaded machines, with the machines it is on
        function _muRows(selected) {
            if (selected !== MU_ALL) return (_muData[selected] || {}).users || [];
            const byId = new Map();
            for (const n of _muLoadedNames()) {
                for (const u of _muData[n].users) {
                    let r = byId.get(u.user_id);
                    if (!r) { r = { ...u, machines: [], fingersBy: {} }; byId.set(u.user_id, r); }
                    if (!r.name && u.name) r.name = u.name;
                    r.machines.push(n);
                    if (u.fingers) r.fingersBy[n] = u.fingers;
                }
            }
            return [...byId.values()].sort((a, b) => _muUidCmp(a.user_id, b.user_id));
        }

        function _muStatusBadge(status) {
            if (!status) return '<span style="color:var(--text-3);font-style:italic;">Not in ERP</span>';
            if (status === 'Active') return '<span class="badge-matched">Active</span>';
            if (status === 'Left') return '<span class="badge-unmatched">Left</span>';
            return `<span style="background:var(--bg);color:var(--text-2);padding:2px 8px;border-radius:10px;font-size:11px;">${escapeHtml(status)}</span>`;
        }

        // Fingerprint templates on the device (index 0..9, read with the user list)
        const FINGER_NAMES = ['Left Little', 'Left Ring', 'Left Middle', 'Left Index', 'Left Thumb',
                              'Right Thumb', 'Right Index', 'Right Middle', 'Right Ring', 'Right Little'];

        function _muFingerText(fids) {
            return `${fids.length}${fids.length ? ' · ' + fids.join(', ') : ''}`;
        }

        function _muFingersCell(u, isAll) {
            if (!isAll) {
                if (!u.fingers) return '<td style="color:var(--text-3);">—</td>';   // older cached list
                const tip = u.fingers.map(f => `${f} = ${FINGER_NAMES[f] || 'Finger ' + f}`).join('\n') || 'No fingerprint on this machine';
                const style = u.fingers.length ? '' : 'color:#dc3545;font-weight:600;';
                return `<td style="white-space:nowrap;${style}" title="${escapeHtml(tip)}">${_muFingerText(u.fingers)}</td>`;
            }
            const per = Object.entries(u.fingersBy || {});
            if (!per.length) return '<td style="color:var(--text-3);">—</td>';
            const texts = new Set(per.map(([, f]) => f.join(',')));
            const tip = per.map(([m, f]) => `${m}: ${_muFingerText(f)}`).join('\n');
            if (texts.size === 1) {
                const f = per[0][1];
                const style = f.length ? '' : 'color:#dc3545;font-weight:600;';
                return `<td style="white-space:nowrap;${style}" title="${escapeHtml(tip)}">${_muFingerText(f)}</td>`;
            }
            return `<td style="white-space:nowrap;color:#b45309;font-weight:600;" title="${escapeHtml(tip)}">⚠ differs</td>`;
        }

        function muRender() {
            const selected = document.getElementById('muMachine').value;
            const q = document.getElementById('muSearch').value.trim().toLowerCase();
            const st = document.getElementById('muStatus').value;
            const fq = document.getElementById('muFingers').value;
            const all = _muRows(selected);
            // finger sets of one row: one machine -> [its list]; All -> one list per loaded machine
            const fingerSets = u => selected === MU_ALL ? Object.values(u.fingersBy || {}) : (u.fingers ? [u.fingers] : []);
            const rows = all.filter(u => {
                if (fq) {
                    const sets = fingerSets(u);
                    if (!sets.length) return false;   // list read before the Fingers column existed
                    if (fq === '0' && !sets.every(f => f.length === 0)) return false;
                    if (fq === '1' && !sets.some(f => f.length === 1)) return false;
                    if (fq === 'differs' && new Set(sets.map(f => f.join(','))).size < 2) return false;
                }
                if (st === 'none' && u.status) return false;
                if (st === 'other' && (!u.status || u.status === 'Active' || u.status === 'Left')) return false;
                if ((st === 'Active' || st === 'Left') && u.status !== st) return false;
                if (!q) return true;
                return [u.user_id, u.name, u.employee, u.employee_name].some(v => (v || '').toLowerCase().includes(q));
            });
            const isAll = selected === MU_ALL;
            const selCell = u => {
                const targets = _muDeleteTargets(u, selected);
                const all = isAll ? u.machines : [selected];
                const title = !targets.length ? MU_PROTECTED
                    : targets.length < all.length ? `Only from: ${targets.join(', ')} (${MU_PROTECTED.toLowerCase()})` : '';
                return `<td><input type="checkbox" class="mu-sel" data-uid="${escapeHtml(u.user_id)}"
                    ${!targets.length ? 'disabled' : ''} ${targets.length && _muSelected.has(u.user_id) ? 'checked' : ''}
                    ${title ? `title="${escapeHtml(title)}"` : ''}></td>`;
            };
            const erpCells = u => `
                <td>${escapeHtml(u.employee || '')}</td>
                <td>${escapeHtml(u.employee_name || '')}</td>
                <td>${_muStatusBadge(u.status)}</td>
                <td style="white-space:nowrap;">${escapeHtml(u.relieving_date || '')}</td>
                <td>${escapeHtml(u.custom_group || '')}</td>`;
            const erpHead = '<th>Employee</th><th>ERP Name</th><th>ERP Status</th><th>Relieving</th><th>Group</th>';
            const selHead = '<th style="width:28px;"><input type="checkbox" id="muSelAll" title="Select all shown (deletable)"></th>';
            document.getElementById('muHead').innerHTML = isAll
                ? `<tr>${selHead}<th>#</th><th>User ID</th><th>Name on Device</th><th title="Fingerprint templates: count · finger indexes 0-9 (hover for names / per machine)">Fingers</th>${erpHead}<th>On Machines</th></tr>`
                : `<tr>${selHead}<th>#</th><th>UID</th><th>User ID</th><th>Name on Device</th><th>Privilege</th><th>PIN</th><th>Card</th><th title="Fingerprint templates: count · finger indexes 0-9 (hover for names)">Fingers</th>${erpHead}</tr>`;
            document.getElementById('muBody').innerHTML = rows.length ? rows.map((u, i) => isAll ? `
                <tr>${selCell(u)}<td>${i + 1}</td><td style="font-family:monospace;">${escapeHtml(u.user_id)}</td>
                    <td>${escapeHtml(u.name)}</td>${_muFingersCell(u, true)}${erpCells(u)}
                    <td title="${escapeHtml(u.machines.join(', '))}">${u.machines.length} · ${escapeHtml(u.machines.join(', '))}</td></tr>` : `
                <tr>${selCell(u)}<td>${i + 1}</td><td style="font-family:monospace;">${u.uid}</td>
                    <td style="font-family:monospace;">${escapeHtml(u.user_id)}</td>
                    <td>${escapeHtml(u.name)}</td><td>${escapeHtml(u.privilege)}</td>
                    <td>${u.has_password ? 'Yes' : ''}</td><td style="font-family:monospace;">${escapeHtml(u.card)}</td>${_muFingersCell(u, false)}${erpCells(u)}</tr>`).join('')
                : `<tr><td colspan="${isAll ? 11 : 14}" style="text-align:center;color:var(--text-3);">No users match</td></tr>`;
            document.getElementById('muSelAll').addEventListener('change', ev => {
                document.querySelectorAll('#muBody .mu-sel:not(:disabled)').forEach(b => {
                    b.checked = ev.target.checked;
                    if (b.checked) _muSelected.add(b.dataset.uid); else _muSelected.delete(b.dataset.uid);
                });
                _muUpdateSelUi();
            });
            _muUpdateSelUi();
            document.getElementById('muCount').textContent = `${rows.length} / ${all.length} users`;
            const names = isAll ? _muLoadedNames() : [selected];
            const reads = names.map(n => (_muData[n] || {}).read_at).filter(Boolean).sort();
            document.getElementById('muInfo').textContent = !reads.length ? ''
                : isAll ? `${names.length} machines · read ${reads[0]} → ${reads[reads.length - 1]}`
                : `Read from device at ${reads[0]}`;
        }

        async function muDelete() {
            const selected = document.getElementById('muMachine').value;
            const ops = [];   // [{user_id, machines}] — only machines the rule allows
            let skipped = 0, doorOps = 0;
            for (const u of _muRows(selected).filter(r => _muSelected.has(r.user_id))) {
                const all = selected === MU_ALL ? u.machines : [selected];
                const targets = _muDeleteTargets(u, selected);
                skipped += all.length - targets.length;
                doorOps += targets.filter(m => _muData[m].is_door_control).length;
                if (targets.length) ops.push({ user_id: u.user_id, machines: targets });
            }
            if (!ops.length) { bsyncAlert('Nothing deletable is selected.'); return; }
            const nOps = ops.reduce((n, o) => n + o.machines.length, 0);
            const machines = [...new Set(ops.flatMap(o => o.machines))];
            let msg = `Delete ${ops.length} user(s) from ${machines.length} machine(s) — ${nOps} deletion(s)?\n`;
            if (doorOps) msg += `\n🚪 ${doorOps} on door controllers: those people will no longer open the door.`;
            if (skipped) msg += `\n${skipped} skipped: employees still working are never deleted from attendance machines.`;
            msg += '\n\nThis cannot be undone on the device. Fingerprints stored in ERPNext are kept (can be re-synced).';
            if (!await bsyncConfirm(msg)) return;

            const btn = document.getElementById('muDeleteBtn');
            const statusEl = document.getElementById('machinesGlobalStatus');
            btn.dataset.busy = '1'; btn.disabled = true; btn.textContent = '⏳ Deleting...';
            try {
                const r = await callPost('customize_erpnext.network.biometric.biometric_sync.delete_users_from_machines',
                    { users_json: JSON.stringify(ops) });
                if (r.status !== 'success') throw new Error(r.message || 'Delete failed');
                const d = await pollJobStatus(r.job_id, d => {
                    statusEl.textContent = d.phase || '';
                    btn.textContent = `⏳ ${d.progress_pct || 0}%`;
                });
                const res = d.results || [];
                const failed = res.filter(x => !x.success);
                statusEl.textContent = `🗑 ${res.length - failed.length} deleted / ${failed.length} failed — re-reading ${machines.length} machine(s)...`;
                _muSelected.clear();
                // re-read the touched machines so the table (and the xlsx cache) match the devices
                await Promise.allSettled(machines.map(n => _muLoad(n)));
                _muRefreshView();
                statusEl.textContent = `🗑 ${res.length - failed.length} deleted / ${failed.length} failed`;
                bsyncAlert(`Done: ${res.length - failed.length} OK / ${failed.length} failed`
                    + (failed.length ? '\n\n' + failed.slice(0, 20).map(x => `${x.user_id} ← ${x.machine}: ${x.message}`).join('\n')
                        + (failed.length > 20 ? `\n… and ${failed.length - 20} more` : '') : ''));
            } catch (e) {
                statusEl.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(e.message)}</span>`;
                bsyncAlert('Delete failed: ' + e.message);
            } finally {
                delete btn.dataset.busy;
                _muUpdateSelUi();
            }
        }

        async function muDownload() {
            const selected = document.getElementById('muMachine').value;
            const names = selected === MU_ALL ? _muLoadedNames() : (_muData[selected] ? [selected] : []);
            if (!names.length) { bsyncAlert('Load a user list first'); return; }
            const btn = document.getElementById('muDownloadBtn');
            // the server builds the file from its cached copy (30 min) — refresh old lists first,
            // a download error would replace the whole page with a raw error
            const stale = names.filter(n => Date.now() - _muData[n].loaded_at > MU_MAX_AGE_MS);
            if (stale.length) {
                btn.disabled = true; btn.textContent = '⏳ Re-reading...';
                const res = await Promise.allSettled(stale.map(n => _muLoad(n)));
                btn.disabled = false; btn.textContent = '⬇ Download xlsx';
                const failed = res.map((r, i) => r.status === 'rejected' ? `${stale[i]}: ${r.reason && r.reason.message}` : null).filter(Boolean);
                if (failed.length) {
                    _muRefreshView();
                    bsyncAlert('Could not re-read (list older than 25 min):\n' + failed.join('\n'));
                    return;
                }
                muRender();
            }
            open_url_post('/api/method/customize_erpnext.network.biometric.biometric_sync.download_machine_users_xlsx',
                { machine_names: JSON.stringify(names) });
        }

        // ════════════════════════════════════════════════════════════════════════════
        // TAB 6 — MANUAL RE-SYNC (device/MongoDB/OT re-sync + delete OT)
        // ════════════════════════════════════════════════════════════════════════════

        let _rsMachinesLoaded = false;
        let _rsRunning = false;

        function rsInitTab() {
            if (!_rsMachinesLoaded) { _rsMachinesLoaded = true; rsLoadMachines(); }
            const today = new Date().toISOString().slice(0, 10);
            ['rsDevFrom', 'rsDevTo', 'rsMongoFrom', 'rsMongoTo', 'rsOtFrom', 'rsOtTo', 'rsDelFrom', 'rsDelTo'].forEach(id => {
                const el = document.getElementById(id);
                if (el && !el.value) el.value = today;
            });
            if (window.is_system_manager) document.getElementById('rsDeleteOtCard').style.display = '';
        }

        async function rsLoadMachines() {
            const listEl = document.getElementById('rsMachineList');
            try {
                const msg = await callGet('customize_erpnext.network.biometric.fingerprint.get_enabled_attendance_machines');
                if (!msg || !msg.success || !msg.machines) throw new Error((msg && msg.message) || 'Failed to load machines');
                listEl.innerHTML = msg.machines.map(m => {
                    const mname = m.name || m.device_name;
                    const online = m.connection_status === 'online';
                    return `
                    <div class="machine-item">
                        <input type="checkbox" class="rs-machine-cb" value="${escapeHtml(mname)}" ${online ? 'checked' : ''}>
                        <span class="machine-item-label">${escapeHtml(m.device_name || mname)}
                            <small style="color:var(--text-3)">${escapeHtml(m.ip_address || '')}</small></span>
                        <span class="badge">${online ? '🟢' : '🔴'}</span>
                    </div>`;
                }).join('');
            } catch (e) {
                listEl.innerHTML = `<div class="alert alert-warning">❌ ${escapeHtml(e.message)}</div>`;
            }
        }

        function rsSelectAllMachines(checked) {
            root.querySelectorAll('.rs-machine-cb').forEach(cb => { cb.checked = checked; });
        }

        // Generic runner: submit whitelisted method returning {job_id}, then poll into
        // the shared progress card. One job at a time for this tab.
        async function rsRunJob(btnId, btnLabel, method, args) {
            if (_rsRunning) return;
            const btn = document.getElementById(btnId);
            const phaseEl = document.getElementById('rsProgressPhase');
            const barEl = document.getElementById('rsProgressBar');
            const logEl = document.getElementById('rsResultLog');
            document.getElementById('rsProgressSection').classList.add('visible');
            logEl.innerHTML = '';
            const log = (cls, text) => {
                const d = document.createElement('div');
                d.className = cls; d.textContent = text;
                logEl.appendChild(d); logEl.scrollTop = logEl.scrollHeight;
            };

            _rsRunning = true;
            _syncRunningCount++;
            btn.disabled = true; btn.textContent = '⏳ Running...';
            barEl.style.width = '0%';
            try {
                const msg = await callPost(method, args);
                if (msg.status !== 'success') throw new Error(msg.message || 'Failed to submit job');
                log('info-line', `Job ${msg.job_id} submitted — waiting for worker...`);
                let lastCount = 0;
                const d = await pollJobStatus(msg.job_id, dd => {
                    phaseEl.textContent = dd.phase || '';
                    barEl.style.width = (dd.progress_pct || 0) + '%';
                    (dd.results || []).slice(lastCount).forEach(r =>
                        log(r.success ? 'ok' : 'fail',
                            `${r.success ? '✓' : '✗'} [${r.machine}]${r.user_id && r.user_id !== '-' ? ' ' + r.user_id + ':' : ''} ${r.message}`));
                    lastCount = (dd.results || []).length;
                });
                barEl.style.width = '100%';
                phaseEl.textContent = d.phase || '✅ Done';
                log('info-line', `\n=== ${d.phase || 'DONE'} ===`);
                return d;
            } catch (e) {
                phaseEl.textContent = '❌ ' + e.message;
                log('fail', '❌ ' + e.message);
            } finally {
                _rsRunning = false;
                _syncRunningCount--;
                btn.disabled = false; btn.textContent = btnLabel;
            }
        }

        async function rsRunDeviceResync() {
            const machines = [...root.querySelectorAll('.rs-machine-cb:checked')].map(cb => cb.value);
            const from = document.getElementById('rsDevFrom').value;
            const to = document.getElementById('rsDevTo').value;
            if (!machines.length) { bsyncAlert('Select at least one machine'); return; }
            if (!from || !to) { bsyncAlert('Pick a date range'); return; }
            if (!await bsyncConfirm(`Re-sync ${machines.length} machine(s) for ${from} → ${to}?\nExisting checkins are skipped automatically.`)) return;
            rsRunJob('rsDevBtn', '▶ Re-sync from devices',
                'customize_erpnext.network.biometric.resync.resync_device_logs',
                { machine_names_json: JSON.stringify(machines), from_date: from, to_date: to });
        }

        async function rsRunMongoResync() {
            const from = document.getElementById('rsMongoFrom').value;
            const to = document.getElementById('rsMongoTo').value;
            if (!from || !to) { bsyncAlert('Pick a date range'); return; }
            if (!await bsyncConfirm(`Sync MongoDB checkins for ${from} → ${to}?`)) return;
            rsRunJob('rsMongoBtn', '▶ Sync from MongoDB',
                'customize_erpnext.network.biometric.mongodb_sync.resync_mongodb_logs',
                { from_date: from, to_date: to });
        }

        async function rsRunOtSync() {
            const from = document.getElementById('rsOtFrom').value;
            const to = document.getElementById('rsOtTo').value;
            if (!from || !to) { bsyncAlert('Pick an OT date range'); return; }
            if (!await bsyncConfirm(`Sync OT registrations from MongoDB for OT dates ${from} → ${to}?`)) return;
            rsRunJob('rsOtBtn', '▶ Sync OT from MongoDB',
                'customize_erpnext.network.biometric.mongodb_sync.sync_ot_from_mongodb',
                { from_date: from, to_date: to });
        }

        async function rsPreviewDeleteOt() {
            const from = document.getElementById('rsDelFrom').value;
            const to = document.getElementById('rsDelTo').value;
            const el = document.getElementById('rsDelPreview');
            const zone = document.getElementById('rsDelConfirmZone');
            zone.style.display = 'none';
            document.getElementById('rsDelConfirm').value = '';
            document.getElementById('rsDelBtn').disabled = true;
            if (!from || !to) { bsyncAlert('Pick a date range'); return; }
            el.innerHTML = '⏳ Loading preview...';
            try {
                const msg = await callPost('customize_erpnext.network.biometric.resync.preview_delete_ot',
                    { from_date: from, to_date: to });
                if (msg.status !== 'success') throw new Error(msg.message || 'Preview failed');
                let html = `<div style="margin-bottom:6px;"><strong style="color:#c0392b;">${msg.detail_count}</strong>
                    OT detail row(s) in <strong>${msg.parent_count}</strong> registration(s) will be affected.</div>`;
                if (msg.sample && msg.sample.length) {
                    html += `<div class="all-info-table-wrap"><table>
                        <thead><tr><th>Registration</th><th>Employee</th><th>Name</th><th>Date</th><th>Begin</th><th>End</th></tr></thead>
                        <tbody>${msg.sample.map(r => `
                            <tr><td>${escapeHtml(r.parent)}</td><td>${escapeHtml(r.employee || '')}</td>
                            <td>${escapeHtml(r.employee_name || '')}</td><td>${escapeHtml(r.date)}</td>
                            <td>${escapeHtml(r.begin_time)}</td><td>${escapeHtml(r.end_time)}</td></tr>`).join('')}
                        </tbody></table></div>`;
                    if (msg.detail_count > msg.sample.length) {
                        html += `<div style="color:var(--text-3);font-size:12px;">Showing first ${msg.sample.length} of ${msg.detail_count} rows.</div>`;
                    }
                }
                el.innerHTML = html;
                zone.style.display = msg.detail_count > 0 ? '' : 'none';
            } catch (e) {
                el.innerHTML = `<span style="color:#dc3545;">❌ ${escapeHtml(e.message)}</span>`;
            }
        }

        function rsDelConfirmInput() {
            document.getElementById('rsDelBtn').disabled =
                document.getElementById('rsDelConfirm').value !== 'DELETE';
        }

        async function rsRunDeleteOt() {
            const from = document.getElementById('rsDelFrom').value;
            const to = document.getElementById('rsDelTo').value;
            const confirmText = document.getElementById('rsDelConfirm').value;
            if (!await bsyncConfirm(`⚠️ PERMANENTLY delete OT detail rows for ${from} → ${to}?\nThis cannot be undone.`)) return;
            rsRunJob('rsDelBtn', '🗑 Delete OT',
                'customize_erpnext.network.biometric.resync.delete_ot',
                { from_date: from, to_date: to, confirm_text: confirmText });
        }


        // ── khởi tạo (trước là DOMContentLoaded) ─────────────────────────────────────
        loadSyncStatus();
            loadMachinesForFingerprint();

        Object.assign(bsync, { _parseFrappeError, appendResultLog, applyEmployeeFilter, buildProgressRow, callGet, callPost, clearEmployeeFilter, del43Delete, del43FindEmp, del43PickCandidate, del43RenderFind, del43RenderPreview, del43ResetPreview, del43RunDeleteJob, del43Scan, del43SelectAll, del43SpecificDelete, escapeHtml, filterLines, fp41LoadEmployees, fp41MachineScopeChange, fp41RenderEmpTable, fp41RenderMachines, fp41SelectAllMachines, fp41StartSync, fp41UpdateSyncBtn, loadLog, loadLogFiles, loadSyncStatus, renderSyncStatus, toggleRawLog, loadMachineCards, loadMachinesForFingerprint, loadMasterUsers, machineGetInfo, machineReboot, machineSyncTime, machineShowUsers, machinesLoadAllInfo, machinesLoadUsersAll, machinesRebootAll, machinesRefresh, machinesScopeChange, machinesSyncTimeAll, muDelete, muDownload, muMachineChange, muRender, onFp41ScopeChange, pollJobStatus, pollSyncJob, renderMachineCards, renderMasterDropdown, renderTargetMachines, renderUserTable, rsDelConfirmInput, rsInitTab, rsLoadMachines, rsPreviewDeleteOt, rsRunDeleteOt, rsRunDeviceResync, rsRunJob, rsRunMongoResync, rsRunOtSync, rsSelectAllMachines, runPhase2, selectAllTargets, selectAllUsers, setProgressBar, startSync, switchTab, updateSyncButton });
};
