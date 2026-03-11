// customize_erpnext/health_check/page/health_check_app/health_check_app.js
//
// Health Check Web App - Main Application
// Route: /health-check-app
//
// Features:
//   - Dashboard with realtime stats, charts by Section & Group
//   - Scan forms for distribute (phát HS) and collect (thu HS)
//   - Employee list with search & filter
//   - Late report
//   - Realtime updates via Socket.IO (frappe.realtime)

const API_BASE =
    "customize_erpnext.health_check_up.api.health_check_api";

// Vietnamese labels - ALL user-facing text
const L = {
    app_title: "Quản lý Khám Sức Khỏe",
    select_date: "Chọn ngày khám",
    tab_dashboard: "Tổng quan",
    tab_distribute: "Phát Hồ Sơ",
    tab_collect: "Thu Hồ Sơ",
    tab_list: "Danh Sách NV",
    tab_late: "Trễ Giờ",
    stat_total: "Tổng nhân viên",
    stat_distributed: "Đã phát HS",
    stat_completed: "Hoàn thành",
    stat_in_exam: "Đang khám",
    stat_not_started: "Chưa khám",
    stat_xray: "X-Quang",
    stat_gynec: "Phụ khoa",
    stat_pregnant: "Mang thai",
    chart_by_section: "Tiến độ theo Section",
    chart_by_group: "Tiến độ theo Group",
    chart_overview: "Tổng quan trạng thái",
    scan_placeholder: "Scan hoặc nhập mã hồ sơ / mã nhân viên...",
    btn_distribute: "⚡ Ghi nhận phát HS",
    btn_collect: "⚡ Ghi nhận thu HS",
    lbl_xray: "X-Quang",
    lbl_gynec: "Phụ khoa",
    msg_success: "✓ Thành công",
    msg_updated: "↻ Đã cập nhật lại",
    msg_not_found: "✗ Không tìm thấy",
    msg_error: "Lỗi",
    msg_input_required: "Vui lòng nhập mã hồ sơ hoặc mã nhân viên",
    msg_confirm_overwrite: "Đã có dữ liệu. Bạn có muốn cập nhật lại?",
    col_stt: "#",
    col_code: "Mã HS",
    col_emp: "Mã NV",
    col_name: "Họ tên",
    col_gender: "Giới tính",
    col_group: "Group",
    col_dist: "Phát HS",
    col_coll: "Thu HS",
    col_xray: "X-Ray",
    col_gynec: "PK",
    col_status: "Trạng thái",
    col_time_diff: "Chênh lệch",
    status_pending: "Chưa khám",
    status_distributed: "Đã phát HS",
    status_completed: "Hoàn thành",
    filter_all: "Tất cả",
    search_placeholder: "Tìm theo mã, tên, group...",
    recent_scans: "Lịch sử scan gần đây",
    no_results: "Không tìm thấy kết quả",
    loading: "Đang tải dữ liệu...",
    settings_title: "⚙️ Cấu hình thời gian",
    allowed_late_dist: "Phút khám trễ cho phép",
    allowed_late_coll: "Phút nộp HS trễ cho phép",
    allowed_early_dist: "Phút khám sớm cho phép",
    btn_save: "Lưu",
    btn_reset: "Mặc định",
    stat_late_dist: "Trễ giờ phát HS",
    stat_late_coll: "Trễ giờ thu HS",
};

// ============================================================
// App State
// ============================================================
const state = {
    currentDate: null,
    dates: [],
    records: [],
    stats: {},
    groups: [],
    sections: [],
    activeTab: "dashboard",
    searchQuery: "",
    statusFilter: "all",
    scanHistory: [],
    // Dashboard filters
    dashFilterStartTime: "all",
    dashFilterSection: "all",
    dashFilterGroup: "all",
    // Settings
    allowedLateDistribute: 10,
    allowedLateCollect: 0,
    allowedEarlyDistribute: 10,
    chartLayout: "vertical", // 'vertical' or 'horizontal'
    // Sort
    sortField: null,
    sortOrder: "asc",
};

// ============================================================
// Page Setup
// ============================================================
frappe.pages["health-check-up-management"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: L.app_title,
        single_column: true,
    });

    // Add download excel button
    page.add_inner_button("Tải file Excel", () => downloadExcel());

    // Build layout
    $(page.body).html(buildLayout());

    // Setup Date Select Event
    $("#hc-date-select").on("change", function () {
        const val = $(this).val();
        if (val && val !== state.currentDate) {
            state.currentDate = val;
            loadData(state.currentDate);
        }
    });

    // Load dates then data
    loadDates().then(() => {
        if (state.dates.length > 0) {
            state.currentDate = state.dates[0];

            // Populate our native select
            const $select = $("#hc-date-select");
            $select.empty();
            state.dates.forEach(d => {
                const label = frappe.datetime.str_to_user(d);
                $select.append(`<option value="${d}">${label}</option>`);
            });
            $select.val(state.currentDate);

            loadData(state.currentDate);
        }
    });

    // Setup tab clicks
    setupTabNavigation();

    // Subscribe to realtime events
    setupRealtime();
    setupPollingAutoSync();

    // Start clock
    startClock();
};

function downloadExcel() {
    if (!state.records || state.records.length === 0) {
        frappe.msgprint("Không có dữ liệu để tải xuống.");
        return;
    }

    const reportWindow = window.open(`/api/method/customize_erpnext.health_check_up.api.health_check_api.get_excel_data?date=${state.currentDate}`);
}

frappe.pages["health-check-up-management"].on_page_show = function () {
    // Re-subscribe realtime when returning to page
    setupRealtime();
    setupPollingAutoSync();
};

frappe.pages["health-check-up-management"].on_page_hide = function () {
    // Unsubscribe to avoid memory leaks
    frappe.realtime.off("health_check_update");
    if (window.hcAutoSyncInterval) clearInterval(window.hcAutoSyncInterval);
};

// ============================================================
// Layout Builder
// ============================================================
function buildLayout() {
    return `
    <div class="hc-app">
        <!-- Header Bar -->
        <div class="hc-header">
            <div class="hc-header-left">
                <span class="hc-clock" id="hc-clock"></span> 
                <span class="hc-mini-bar-text" id="hc-mini-bar-text">Tổng quan chung</span>
                <div class="hc-mini-bar-wrap" id="hc-mini-bar" title="Tổng quan" style="display: none;"></div>
            </div>
            <div class="hc-tabs" id="hc-tabs">
                <span class="hc-mini-bar-text" id="hc-mini-bar-text">Chọn ngày khám</span>
                <select class="hc-date-select" id="hc-date-select" style="margin-right: 8px;"></select>
                <button class="hc-tab active" data-tab="dashboard">📊 ${L.tab_dashboard}</button>
                <button class="hc-tab" data-tab="distribute">📤 ${L.tab_distribute}</button>
                <button class="hc-tab" data-tab="collect">📥 ${L.tab_collect}</button>
                <button class="hc-tab" data-tab="list">📋 ${L.tab_list}</button>
            </div>
        </div>

        <!-- Content Area -->
        <div class="hc-content" id="hc-content">
            <div class="hc-loading" id="hc-loading">${L.loading}</div>
        </div>
    </div>`;
}

// ============================================================
// Data Loading
// ============================================================
async function loadDates() {
    try {
        const r = await frappe.call({
            method: `${API_BASE}.get_health_check_dates`,
        });
        state.dates = r.message || [];
    } catch (e) {
        frappe.msgprint("Lỗi tải danh sách ngày: " + e.message);
    }
}

async function loadData(date) {
    showLoading();
    try {
        const r = await frappe.call({
            method: `${API_BASE}.get_health_check_data`,
            args: { date },
        });
        if (r.message) {
            state.records = r.message.records || [];
            state.stats = r.message.stats || {};
            state.groups = r.message.groups || [];
            state.sections = r.message.sections || [];
            state.currentDate = r.message.date;
            updateDateDisplay();

            // Disable distribute and collect tabs if current date > record date
            const today = frappe.datetime.get_today();
            if (today > state.currentDate) {
                $(".hc-tab[data-tab='distribute']").addClass("hc-tab-disabled");
                $(".hc-tab[data-tab='collect']").addClass("hc-tab-disabled");
                if (state.activeTab === "distribute" || state.activeTab === "collect") {
                    state.activeTab = "dashboard";
                    $(".hc-tab").removeClass("active");
                    $(".hc-tab[data-tab='dashboard']").addClass("active");
                }
            } else {
                $(".hc-tab[data-tab='distribute']").removeClass("hc-tab-disabled");
                $(".hc-tab[data-tab='collect']").removeClass("hc-tab-disabled");
            }
        }
    } catch (e) {
        frappe.msgprint("Lỗi tải dữ liệu: " + e.message);
    }
    renderActiveTab();
    renderMiniBar();
}

// ============================================================
// Tab Navigation
// ============================================================
function setupTabNavigation() {
    $(document).on("click", ".hc-tab", function () {
        if ($(this).hasClass("hc-tab-disabled")) {
            frappe.show_alert({ message: "Đợt khám sức khỏe này đã kết thúc. Bạn không thể thu hoặc phát HS.", indicator: "orange" });
            return;
        }

        $(".hc-tab").removeClass("active");
        $(this).addClass("active");
        state.activeTab = $(this).data("tab");
        renderActiveTab();
    });
}

function renderMiniBar() {
    if (!state.records || state.records.length === 0) {
        $("#hc-mini-bar").hide();
        return;
    }
    const stats = calcFilteredStats(state.records);
    if (stats.total === 0) {
        $("#hc-mini-bar").hide();
        return;
    }

    const pctComp = (stats.completed / stats.total) * 100;
    const pctExam = (stats.in_exam / stats.total) * 100;
    const pctNot = (stats.not_started / stats.total) * 100;

    const html = `
        <div style="width: ${pctComp}%; background: var(--hc-green);" title="Hoàn thành: ${stats.completed}"></div>
        <div style="width: ${pctExam}%; background: var(--hc-yellow);" title="Đang khám: ${stats.in_exam}"></div>
        <div style="width: ${pctNot}%; background: var(--hc-red);" title="Chưa khám: ${stats.not_started}"></div>
    `;

    const $bar = $("#hc-mini-bar");
    $bar.html(html).css("display", "flex");
    $bar.attr("title", `Tổng quan tiến độ:\n- Hoàn thành: ${stats.completed}\n- Đang khám: ${stats.in_exam}\n- Chưa khám: ${stats.not_started}`);
}

function renderActiveTab() {
    const $content = $("#hc-content");
    switch (state.activeTab) {
        case "dashboard":
            $content.html(renderDashboard());
            setupDashboardFilters();
            renderCharts();
            break;
        case "distribute":
            $content.html(renderScanForm("distribute"));
            setupScanForm("distribute");
            break;
        case "collect":
            $content.html(renderScanForm("collect"));
            setupScanForm("collect");
            break;
        case "list":
            $content.html(renderEmployeeList());
            setupListEvents();
            break;
    }
}

// ============================================================
// Dashboard Render
// ============================================================
function renderDashboard() {
    // Get distinct values for filter dropdowns
    const startTimes = [...new Set(state.records.map(r => formatTime(r.start_time)).filter(t => t !== "—"))].sort();
    const sectionList = [...new Set(state.records.map(r => r.custom_section).filter(Boolean))].sort();
    const groupList = [...new Set(state.records.map(r => r.custom_group).filter(Boolean))].sort();

    // Apply dashboard filters
    const filtered = getDashboardFilteredRecords();
    const s = calcFilteredStats(filtered);

    return `
    <div class="hc-dashboard">
        <!-- Filter Bar -->
        <div class="hc-dash-filters">
            <div class="hc-dash-filter-item">
                <label class="hc-dash-filter-label">⏰ Giờ bắt đầu</label>
                <select class="hc-dash-filter-select" id="dash-filter-time">
                    <option value="all">Tất cả</option>
                    ${startTimes.map(t => `<option value="${t}" ${state.dashFilterStartTime === t ? 'selected' : ''}>${t}</option>`).join('')}
                </select>
            </div>
            <div class="hc-dash-filter-item">
                <label class="hc-dash-filter-label">🏢 Section</label>
                <select class="hc-dash-filter-select" id="dash-filter-section">
                    <option value="all">Tất cả</option>
                    ${sectionList.map(s => `<option value="${s}" ${state.dashFilterSection === s ? 'selected' : ''}>${s}</option>`).join('')}
                </select>
            </div>
            <div class="hc-dash-filter-item">
                <label class="hc-dash-filter-label">👥 Group</label>
                <select class="hc-dash-filter-select" id="dash-filter-group">
                    <option value="all">Tất cả</option>
                    ${groupList.map(g => `<option value="${g}" ${state.dashFilterGroup === g ? 'selected' : ''}>${g}</option>`).join('')}
                </select>
            </div>
            <button class="hc-dash-filter-reset" id="dash-filter-reset" title="Xóa bộ lọc">✕ Xóa lọc</button>
            
            <div style="margin-left: auto; display: flex; gap: 8px;">
                <select class="hc-dash-filter-select" id="dash-filter-layout" title="Hướng biểu đồ">
                    <option value="vertical" ${state.chartLayout === 'vertical' ? 'selected' : ''}>📊 Dọc</option>
                    <option value="horizontal" ${state.chartLayout === 'horizontal' ? 'selected' : ''}>≡ Ngang</option>
                </select>
                <button class="hc-dash-filter-reset" id="dash-settings-btn" title="Cấu hình">⚙ Cấu hình</button>
            </div>
        </div>

        <!-- Stat Cards -->
        <div id="hc-stats-wrapper">
            <div class="hc-stats-grid mb-3">
                ${statCard("total", L.stat_total, s.total, null, "cyan", "👥")}            
                ${statCard("completed", L.stat_completed, s.completed, s.total, "green", "✅")}
                ${statCard("in_exam", L.stat_in_exam, s.in_exam, s.total, "yellow", "🔄")}
                ${statCard("not_started", L.stat_not_started, s.not_started, s.total, "red", "❌")}
            </div>
            
            <div class="hc-stats-grid mb-3">
                ${statCard("distributed", L.stat_distributed, s.distributed, s.total, "blue", "📤")}
                ${statCard("late_dist", L.stat_late_dist, s.late_dist, s.total, "red", "⏰")}
                ${statCard("late_coll", L.stat_late_coll, s.late_coll, s.total, "orange", "⏳")}
                ${statCard("pregnant", L.stat_pregnant, s.pregnant, s.total, "purple", "🤰")}
            </div>
        </div>

        <!-- Charts (vertical stack: Group → Section) -->
        <div class="hc-charts-stack">
            <div class="hc-chart-card">
                <div class="hc-chart-title">${L.chart_by_group}</div>
                <div id="chart-group"></div>
            </div>
            <div class="hc-chart-card">
                <div class="hc-chart-title">${L.chart_by_section}</div>
                <div id="chart-section"></div>
            </div>
        </div>

        
    </div>`;
}

function getDashboardFilteredRecords() {
    let records = [...state.records];

    if (state.dashFilterStartTime !== "all") {
        records = records.filter(r => formatTime(r.start_time) === state.dashFilterStartTime);
    }
    if (state.dashFilterSection !== "all") {
        records = records.filter(r => r.custom_section === state.dashFilterSection);
    }
    if (state.dashFilterGroup !== "all") {
        records = records.filter(r => r.custom_group === state.dashFilterGroup);
    }

    return records;
}

function calcFilteredStats(records) {
    const total = records.length;
    const distributed = records.filter(r => r.start_time_actual).length;
    const completed = records.filter(r => r.end_time_actual).length;

    let late_dist = 0;
    let late_coll = 0;

    records.forEach(r => {
        if (isRecordLateForDistribute(r)) late_dist++;
        if (isRecordLateForCollect(r)) late_coll++;
    });

    return {
        total,
        distributed,
        completed,
        in_exam: distributed - completed,
        not_started: total - distributed,
        x_ray: records.filter(r => r.x_ray).length,
        gynecological_exam: records.filter(r => r.gynecological_exam).length,
        pregnant: records.filter(r => r.pregnant).length,
        late_dist,
        late_coll,
    };
}

function updateDashboardStats() {
    const $wrapper = $("#hc-stats-wrapper");
    if ($wrapper.length === 0) return; // Dashboard not currently visible

    const filtered = getDashboardFilteredRecords();
    const s = calcFilteredStats(filtered);

    $wrapper.html(`
        <div class="hc-stats-group-title">Nhóm 1: Tiến độ chung</div>
        <div class="hc-stats-grid mb-3">
            ${statCard("total", L.stat_total, s.total, null, "cyan", "👥")}    
            ${statCard("completed", L.stat_completed, s.completed, s.total, "green", "✅")}
            ${statCard("in_exam", L.stat_in_exam, s.in_exam, s.total, "yellow", "🔄")}
            ${statCard("not_started", L.stat_not_started, s.not_started, s.total, "red", "❌")}
        </div>
        
        <div class="hc-stats-group-title">Nhóm 2: Thông tin thêm</div>
        <div class="hc-stats-grid mb-3">
            ${statCard("distributed", L.stat_distributed, s.distributed, s.total, "blue", "📤")}
            ${statCard("late_dist", L.stat_late_dist, s.late_dist, s.total, "red", "⏰")}
            ${statCard("late_coll", L.stat_late_coll, s.late_coll, s.total, "orange", "⏳")}
            ${statCard("pregnant", L.stat_pregnant, s.pregnant, s.total, "purple", "🤰")}
        </div>
    `);

    // Re-attach click handlers for stat cards (they get replaced with the HTML above)
    $(".hc-stat-card").off("click").on("click", function () {
        const type = $(this).data("type");
        if (type) showStatModal(type);
    });
}

function setupDashboardFilters() {
    $("#dash-filter-time").on("change", function () {

        state.dashFilterStartTime = $(this).val();
        renderActiveTab();
    });
    $("#dash-filter-section").on("change", function () {
        state.dashFilterSection = $(this).val();
        renderActiveTab();
    });
    $("#dash-filter-group").on("change", function () {
        state.dashFilterGroup = $(this).val();
        renderActiveTab();
    });
    $("#dash-filter-reset").on("click", function () {
        state.dashFilterStartTime = "all";
        state.dashFilterSection = "all";
        state.dashFilterGroup = "all";
        renderActiveTab();
    });
    $("#dash-filter-layout").on("change", function () {
        state.chartLayout = $(this).val();
        renderActiveTab();
    });
    $("#dash-settings-btn").on("click", function () {
        showSettingsDialog();
    });
    $(".hc-stat-card").on("click", function () {
        const type = $(this).data("type");
        if (type) showStatModal(type);
    });
}

function showSettingsDialog() {
    const dialog = new frappe.ui.Dialog({
        title: L.settings_title,
        fields: [
            {
                fieldtype: "Int",
                fieldname: "allowed_late_dist",
                label: L.allowed_late_dist,
                default: state.allowedLateDistribute,
            },
            {
                fieldtype: "Int",
                fieldname: "allowed_late_coll",
                label: L.allowed_late_coll,
                default: state.allowedLateCollect,
            },
            {
                fieldtype: "Int",
                fieldname: "allowed_early_dist",
                label: L.allowed_early_dist,
                default: state.allowedEarlyDistribute,
            }
        ],
        primary_action_label: L.btn_save,
        primary_action(values) {
            state.allowedLateDistribute = values.allowed_late_dist;
            state.allowedLateCollect = values.allowed_late_coll;
            state.allowedEarlyDistribute = values.allowed_early_dist;
            renderActiveTab();
            dialog.hide();
        },
    });

    dialog.add_custom_button(L.btn_reset, () => {
        dialog.set_values({
            allowed_late_dist: 10,
            allowed_late_coll: 0,
            allowed_early_dist: 10
        });
    });

    dialog.show();
}

function getStatModalData(type) {
    const filtered = getDashboardFilteredRecords();
    switch (type) {
        case "total": return filtered;
        case "distributed": return filtered.filter(r => r.start_time_actual);
        case "completed": return filtered.filter(r => r.end_time_actual);
        case "in_exam": return filtered.filter(r => r.start_time_actual && !r.end_time_actual);
        case "not_started": return filtered.filter(r => !r.start_time_actual);
        case "late_dist":
            return filtered.filter(r => isRecordLateForDistribute(r));
        case "late_coll":
            return filtered.filter(r => isRecordLateForCollect(r));
        case "pregnant": return filtered.filter(r => r.pregnant);
        default: return [];
    }
}

function showStatModal(type) {
    const records = getStatModalData(type);

    // Build table HTML
    let tableHtml = `
        <div style="max-height: 400px; overflow-y: auto;">
        <table class="table table-bordered text-sm" style="font-size: 11px;">
            <thead style="position: sticky; top: 0; background: white; z-index: 1;">
                <tr>
                    <th>STT</th>
                    <th>Mã HS</th>
                    <th>Mã NV</th>
                    <th>Họ tên</th>
                    <th>Group</th>
                    <th>TG Phát (Dự kiến)</th>
                    <th>TG Thu (Dự kiến)</th>
                    <th>TG Phát (Thực tế)</th>
                    <th>TG Thu (Thực tế)</th>
                </tr>
            </thead>
            <tbody>
    `;

    if (records.length === 0) {
        tableHtml += `<tr><td colspan="9" class="text-center text-muted">Không có dữ liệu</td></tr>`;
    } else {
        records.forEach((r, i) => {
            tableHtml += `
            <tr>
                <td>${i + 1}</td>
                <td class="hc-mono">${r.hospital_code || ""}</td>
                <td class="hc-mono">${r.employee || ""}</td>
                <td class="hc-bold">${r.employee_name || ""}</td>
                <td>${r.custom_group || ""}</td>
                <td class="hc-mono">${formatTime(r.start_time)}</td>
                <td class="hc-mono">${formatTime(r.end_time)}</td>
                <td class="hc-mono ${r.start_time_actual ? 'hc-green' : 'hc-muted'}">${formatTime(r.start_time_actual)}</td>
                <td class="hc-mono ${r.end_time_actual ? 'hc-green' : 'hc-muted'}">${formatTime(r.end_time_actual)}</td>
            </tr>`;
        });
    }

    tableHtml += `</tbody></table></div>`;

    const dialog = new frappe.ui.Dialog({
        title: `Danh sách nhân viên (${records.length})`,
        size: "extra-large",
    });

    $(dialog.body).html(tableHtml);
    dialog.show();
}

function statCard(type, label, value, total, color, icon) {
    const pct =
        total != null && total > 0
            ? Math.round((value / total) * 100) + "%"
            : "";
    return `
    <div class="hc-stat-card hc-stat-${color} clickable-card" data-type="${type}" style="cursor: pointer;">
        <div class="hc-stat-label">${label}</div>
        <div class="hc-stat-value">${(value || 0).toLocaleString()}</div>
        ${pct ? `<div class="hc-stat-pct">${pct} / ${total}</div>` : ""}
        <div class="hc-stat-icon">${icon}</div>
    </div>`;
}

function renderHorizontalChart(containerId, dataArray, labelField) {
    let maxVal = Math.max(...dataArray.map(d => d.total));
    if (maxVal === 0) maxVal = 1;

    let html = `<div class="hc-hchart">`;
    dataArray.forEach(item => {
        const label = item[labelField];
        const completed = item.completed;
        const in_exam = item.distributed - item.completed;
        const not_started = item.total - item.distributed;
        const pctComp = (completed / maxVal) * 100;
        const pctExam = (in_exam / maxVal) * 100;
        const pctNotSt = (not_started / maxVal) * 100;

        html += `
        <div class="hc-hchart-row">
            <div class="hc-hchart-label" title="${label}">${label} <span class="hc-hchart-val">(${item.total})</span></div>
            <div class="hc-hchart-bars">
                <div class="hc-hchart-bar hc-hchart-bar-comp" style="width: ${pctComp}%" title="Hoàn thành: ${completed}"></div>
                <div class="hc-hchart-bar hc-hchart-bar-exam" style="width: ${pctExam}%" title="Đang khám: ${in_exam}"></div>
                <div class="hc-hchart-bar hc-hchart-bar-none" style="width: ${pctNotSt}%" title="Chưa khám: ${not_started}"></div>
            </div>
        </div>`;
    });
    html += `
        <div class="hc-hchart-legend">
            <span class="hc-hchart-legend-item"><span class="hc-hchart-legend-color hc-bg-comp"></span> ${L.stat_completed}</span>
            <span class="hc-hchart-legend-item"><span class="hc-hchart-legend-color hc-bg-exam"></span> ${L.stat_in_exam}</span>
            <span class="hc-hchart-legend-item"><span class="hc-hchart-legend-color hc-bg-none"></span> ${L.stat_not_started || "Chưa khám"}</span>
        </div>
    </div>`;

    document.getElementById(containerId).innerHTML = html;
}

function renderCharts() {
    // Compute chart data from filtered records
    const filtered = getDashboardFilteredRecords();

    const groups = {};
    const sections = {};
    filtered.forEach((r) => {
        const g = r.custom_group || "Không xác định";
        const s = r.custom_section || "Không xác định";
        if (!groups[g]) groups[g] = { total: 0, distributed: 0, completed: 0 };
        groups[g].total++;
        if (r.start_time_actual) groups[g].distributed++;
        if (r.end_time_actual) groups[g].completed++;
        if (!sections[s]) sections[s] = { total: 0, distributed: 0, completed: 0 };
        sections[s].total++;
        if (r.start_time_actual) sections[s].distributed++;
        if (r.end_time_actual) sections[s].completed++;
    });

    const groupArr = Object.entries(groups).map(([k, v]) => ({ group: k, ...v })).sort((a, b) => a.group.localeCompare(b.group));
    const sectionArr = Object.entries(sections).map(([k, v]) => ({ section: k, ...v })).sort((a, b) => b.total - a.total);

    // Section chart
    if (sectionArr.length > 0) {
        if (state.chartLayout === "horizontal") {
            renderHorizontalChart("chart-section", sectionArr, "section");
        } else if (typeof frappe.Chart !== "undefined") {
            const labels = sectionArr.map((s) => s.section);
            new frappe.Chart("#chart-section", {
                data: {
                    labels: labels,
                    datasets: [
                        { name: L.stat_completed, values: sectionArr.map((s) => s.completed) },
                        { name: L.stat_in_exam, values: sectionArr.map((s) => s.distributed - s.completed) },
                        { name: L.stat_not_started || "Chưa khám", values: sectionArr.map((s) => s.total - s.distributed) },
                    ],
                },
                type: "bar",
                height: 250,
                colors: ["#10b981", "#f59e0b", "#ef4444"],
                barOptions: { stacked: true, spaceRatio: 0.4 },
            });

            // Frappe charts auto-truncates x-axis labels. We override + rotate 45° via CSS style:
            setTimeout(() => {
                document.querySelectorAll("#chart-section .x.axis .tick text").forEach((el, idx) => {
                    if (labels[idx]) el.textContent = labels[idx];
                    el.setAttribute("text-anchor", "end");
                    el.style.transformBox = "fill-box";
                    el.style.transformOrigin = "right center";
                    el.style.transform = "rotate(-45deg)";
                });
            }, 500);
        }
    }

    // Group chart
    if (groupArr.length > 0) {
        if (state.chartLayout === "horizontal") {
            renderHorizontalChart("chart-group", groupArr, "group");
        } else if (typeof frappe.Chart !== "undefined") {
            const labels = groupArr.map((g) => g.group);
            new frappe.Chart("#chart-group", {
                data: {
                    labels: labels,
                    datasets: [
                        { name: L.stat_completed, values: groupArr.map((g) => g.completed) },
                        { name: L.stat_in_exam, values: groupArr.map((g) => g.distributed - g.completed) },
                        { name: L.stat_not_started || "Chưa khám", values: groupArr.map((g) => g.total - g.distributed) },
                    ],
                },
                type: "bar",
                height: 300,
                colors: ["#10b981", "#f59e0b", "#ef4444"],
                barOptions: { stacked: true, spaceRatio: 0.3 },
            });

            setTimeout(() => {
                document.querySelectorAll("#chart-group .x.axis .tick text").forEach((el, idx) => {
                    if (labels[idx]) el.textContent = labels[idx];
                    el.setAttribute("text-anchor", "end");
                    el.style.transformBox = "fill-box";
                    el.style.transformOrigin = "right center";
                    el.style.transform = "rotate(-45deg)";
                });
            }, 500);
        }
    }
}

// ============================================================
// Scan Form Render
// ============================================================
function renderScanForm(mode) {
    const isDist = mode === "distribute";
    return `
    <div class="hc-scan-layout">
        <div class="hc-scan-card">
            <div class="hc-scan-icon">${isDist ? "📤" : "📥"}</div>
            <h2 class="hc-scan-title">
                ${isDist ? L.tab_distribute : L.tab_collect}
            </h2>
            <p class="hc-scan-subtitle">${L.scan_placeholder}</p>

            <div class="hc-scan-type-toggle">
                <label class="hc-radio-label">
                    <input type="radio" name="scan_type_${mode}" value="hospital" checked />
                    <span>Mã Bệnh Viện</span>
                </label>
                <label class="hc-radio-label">
                    <input type="radio" name="scan_type_${mode}" value="employee" />
                    <span>Mã Nhân Viên</span>
                </label>
            </div>

            <input type="text" class="hc-scan-input" id="scan-input"
                   placeholder="${L.scan_placeholder}" autocomplete="off" />

            ${!isDist
            ? `
            <div class="hc-scan-checkboxes" id="scan-checkboxes">
                <label class="hc-checkbox-label" id="lbl-xray">
                    <input type="checkbox" id="chk-xray" checked />
                    <span>🩻 ${L.lbl_xray}</span>
                </label>
                <label class="hc-checkbox-label" id="lbl-gynec">
                    <input type="checkbox" id="chk-gynec" />
                    <span>♀ ${L.lbl_gynec}</span>
                </label>
            </div>`
            : ""
        }

            <textarea class="hc-scan-input" id="scan-note" 
                      placeholder="Ghi chú thêm (không bắt buộc)" rows="2"
                      style="margin-bottom: 24px; font-size: 14px; padding: 10px 14px;resize: none;"></textarea>

            <button class="hc-scan-btn hc-scan-btn-${isDist ? "blue" : "green"}"
                    id="scan-btn">
                ${isDist ? L.btn_distribute : L.btn_collect}
            </button>

            <div class="hc-scan-result" id="scan-result"></div>
        </div>

        <div class="hc-scan-history">
            <div class="hc-scan-history-title">${L.recent_scans}</div>
            <div id="scan-history-list"></div>
        </div>
    </div>`;
}

function setupScanForm(mode) {
    const $input = $("#scan-input");
    const $note = $("#scan-note");
    const $btn = $("#scan-btn");

    populateScanHistory(mode);

    const defaultBtnText = mode === "distribute" ? L.btn_distribute : L.btn_collect;

    // Live Preview & Auto check checkboxes on input change
    $input.on("input", function () {
        const code = $(this).val().trim();
        const scanType = $(`input[name="scan_type_${mode}"]:checked`).val();
        let record = null;

        if (code) {
            if (scanType === "employee" && code.length === 4) {
                record = state.records.find(r => r.employee && r.employee.endsWith(code));
            } else if (scanType === "hospital") {
                // For hospital code, it might be dynamically entered or pasted. 
                // We'll show preview if it exactly matches an existing code.
                record = state.records.find(r => r.hospital_code === code);
            }
        }

        // 1. Update Submit Button Text (Live Preview)
        if (record) {
            const groupText = record.custom_group ? ` - ${record.custom_group}` : "";
            $btn.text(`Ghi nhận: ${record.employee_name}${groupText}`);
        } else {
            $btn.text(defaultBtnText);
        }

        // 2. Auto check checkboxes (Collect Mode Only)
        if (mode === "collect" && record) {
            // X quang: mặc định 0 cho nữ mang thai, còn lại 1
            if (record.pregnant) {
                $("#chk-xray").prop("checked", false);
            } else {
                $("#chk-xray").prop("checked", true);
            }

            // Phụ khoa: mặc định 1 cho nữ, 0 cho nam (ẩn nếu nam)
            const isFemale = record.gender === "Nữ" || record.gender === "Female";
            if (isFemale) {
                $("#lbl-gynec").show();
                $("#chk-gynec").prop("checked", true);
            } else {
                $("#lbl-gynec").hide();
                $("#chk-gynec").prop("checked", false);
            }
        }
    });

    // Also trigger when radio type changes
    $(`input[name="scan_type_${mode}"]`).on("change", function () {
        $input.trigger("input");
    });
    renderHistory();

    // Auto focus
    setTimeout(() => $input.focus(), 100);

    // Enter key
    $input.on("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            doScan(mode);
        }
    });

    // Button click
    $btn.on("click", () => doScan(mode));
}

function populateScanHistory(mode) {
    const timeField = mode === "distribute" ? "start_time_actual" : "end_time_actual";

    // Filter records that have the timeField set
    const scanned = state.records.filter(r => r[timeField]);

    // Sort descending by time
    scanned.sort((a, b) => {
        if (a[timeField] < b[timeField]) return 1;
        if (a[timeField] > b[timeField]) return -1;
        return 0;
    });

    // Take top 50, map to history format
    state.scanHistory = scanned.slice(0, 50).map(r => ({
        time: formatTime(r[timeField]),
        code: r.hospital_code,
        emp: r.employee,
        name: r.employee_name,
        group: r.custom_group,
        mode: mode,
        type: "success", // Default to green since it was already scanned
        xray: r.x_ray,
        gynec: r.gynecological_exam,
        note: r.note
    }));
}

async function doScan(mode) {
    const $input = $("#scan-input");
    const $note = $("#scan-note");
    const code = $input.val().trim();
    const noteText = $note.val().trim();

    if (!code) {
        showScanResult("error", L.msg_input_required);
        return;
    }

    const scanType = $(`input[name="scan_type_${mode}"]:checked`).val();

    if (scanType === "employee") {
        if (code.length !== 4) {
            showScanResult("error", "Vui lòng nhập đúng 4 ký tự cuối của mã nhân viên.");
            $input.val("").focus();
            return;
        }
    } else {
        if (code.length < 2 || code.length > 20) {
            showScanResult("error", "Mã bệnh viện phải từ 2-20 ký tự.");
            $input.val("").focus();
            return;
        }
    }

    const args = { date: state.currentDate };
    if (noteText) {
        args.note = noteText;
    }

    if (scanType === "employee") {
        args.employee = code;
    } else {
        // Default to hospital code
        args.hospital_code = code;
    }

    if (mode === "collect") {
        args.x_ray = $("#chk-xray").is(":checked") ? 1 : 0;
        args.gynecological_exam = $("#chk-gynec").is(":checked") ? 1 : 0;
    }

    const executeCall = async () => {
        try {
            const method = mode === "distribute"
                ? `${API_BASE}.scan_distribute`
                : `${API_BASE}.scan_collect`;

            const r = await frappe.call({ method, args });

            if (r.message && r.message.success) {
                const rec = r.message.record;
                const msgType = r.message.already_existed ? "update" : "success";
                const msgText = r.message.already_existed
                    ? L.msg_updated
                    : L.msg_success;

                showScanResult(msgType, msgText, rec);
                addToHistory(rec, mode, msgType);
            }
        } catch (e) {
            // frappe.throw from server automatically shows msgprint
            showScanResult("error", L.msg_not_found + ": " + code);
        }

        // Reset form
        $input.val("").trigger("input").focus();
        $note.val("");
        if (mode === "collect") {
            $("#chk-xray").prop("checked", true);
            $("#lbl-gynec").show();
            $("#chk-gynec").prop("checked", false);
        }
    };

    // Early check for existing distribution
    let recordItem = null;
    if (state.records && state.records.length > 0) {
        if (scanType === "employee") {
            recordItem = state.records.find(r => r.employee && r.employee.endsWith(code));
        } else {
            recordItem = state.records.find(r => r.hospital_code === code);
        }
    }

    if (recordItem && mode === "distribute" && recordItem.start_time_actual) {
        frappe.confirm(
            `Hồ sơ của <b>${recordItem.employee_name}</b> đã được Phát vào lúc <b>${formatTime(recordItem.start_time_actual)}</b>.<br><br>Bạn có chắc chắn muốn phát lại và ghi đè thời gian hiện tại không?`,
            () => {
                executeCall();
            },
            () => {
                // Use Cancelled
                $input.val("").trigger("input").focus();
                $note.val("");
            }
        );
    } else if (recordItem && mode === "collect" && !recordItem.start_time_actual) {
        // Missing distribution time on collect
        const defaultTime = recordItem.start_time || "07:30:00";

        let d = new frappe.ui.Dialog({
            title: "Thiếu thời gian Phát HS",
            fields: [
                {
                    label: "Hồ sơ này chưa được ghi nhận Phát HS. Vui lòng bổ sung giờ phát thực tế:",
                    fieldtype: "HTML",
                    fieldname: "msg"
                },
                {
                    label: "Giờ Phát HS Thực Tế",
                    fieldname: "manual_start_time",
                    fieldtype: "Time",
                    default: defaultTime,
                    reqd: 1
                }
            ],
            primary_action_label: "Xác nhận & Thu HS",
            primary_action(values) {
                args.manual_start_time = values.manual_start_time;
                d.hide();
                executeCall();
            },
            on_hide() {
                // If user just closed it without confirming, we clear the form
                $input.val("").focus();
                $note.val("");
            }
        });
        d.show();
    } else {
        executeCall();
    }
}

function showScanResult(type, message, record) {
    const colors = {
        success: "green",
        update: "yellow",
        error: "red",
    };
    const color = colors[type] || "red";

    let html = `<div class="hc-result hc-result-${color}">
        <div class="hc-result-msg">${message}</div>`;

    if (record) {
        html += `<div class="hc-result-detail">
            <strong>${record.hospital_code}</strong> —
            ${record.employee} — ${record.employee_name}<br/>
            ${record.custom_section || ""} / ${record.custom_group || ""} —
            ${record.designation || ""}
        </div>`;
    }

    html += `</div>`;
    $("#scan-result").html(html);
}

function addToHistory(record, mode, type) {
    const time = new Date().toLocaleTimeString("vi-VN");
    state.scanHistory.unshift({
        time,
        code: record.hospital_code,
        emp: record.employee,
        name: record.employee_name,
        group: record.custom_group,
        mode,
        type,
        xray: record.x_ray,
        gynec: record.gynecological_exam,
        note: record.note
    });
    // Keep only last 50
    state.scanHistory = state.scanHistory.slice(0, 50);
    renderHistory();
}

function renderHistory() {
    const $list = $("#scan-history-list");
    if (state.scanHistory.length === 0) {
        $list.html(
            '<div class="hc-scan-history-empty">Chưa có lịch sử scan</div>'
        );
        return;
    }
    const html = state.scanHistory
        .map(
            (h) => `
        <div class="hc-history-item hc-history-${h.type}" style="display: flex; align-items: center; gap: 8px; padding: 4px 8px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
            <span class="hc-history-time" style="font-weight: 500; min-width: 60px;">${h.time}</span>
            <span class="hc-history-code" style="color: var(--hc-primary); font-weight: 600; min-width: 50px;">${h.code}</span>
            <span style="color: var(--hc-text-light); min-width: 40px;">${h.emp || ''}</span>
            <span class="hc-history-name" style="font-weight: 600; min-width: 120px; text-overflow: ellipsis; overflow: hidden;">${h.name}</span>
            <span style="color: var(--hc-text-light); min-width: 60px;">${h.group || ''}</span>
            ${h.mode === "collect" ? `
                <span style="color: var(--hc-text-light); min-width: 70px;">${h.xray ? '🩻 X-Quang' : ''}</span>
                <span style="color: var(--hc-text-light); min-width: 75px;">${h.gynec ? '♀ Phụ khoa' : ''}</span>
            ` : ''}
            <span style="color: #f59e0b; font-style: italic; overflow: hidden; text-overflow: ellipsis; flex: 1;">${h.note ? `📝 ${h.note}` : ''}</span>
            <span class="hc-history-mode" style="font-weight: 600; min-width: 30px; text-align: right;">${h.mode === "distribute" ? "Phát" : "Thu"}</span>
        </div>`
        )
        .join("");
    $list.html(html);
}

// ============================================================
// Employee List Render
// ============================================================
function renderEmployeeList() {
    return `
    <div class="hc-list-container">
        <div class="hc-list-toolbar">
            <input type="text" class="hc-search-input" id="list-search"
                   placeholder="${L.search_placeholder}" />
            <div class="hc-filter-btns" id="filter-btns">
                <button class="hc-filter-btn active" data-filter="all">${L.filter_all}</button>
                <button class="hc-filter-btn" data-filter="completed">${L.status_completed}</button>
                <button class="hc-filter-btn" data-filter="distributed">${L.status_distributed}</button>
                <button class="hc-filter-btn" data-filter="pending">${L.status_pending}</button>
                <button class="hc-filter-btn" data-filter="late_dist">${L.stat_late_dist}</button>
                <button class="hc-filter-btn" data-filter="late_coll">${L.stat_late_coll}</button>
            </div>
        </div>
        <div class="hc-table-wrap" id="hc-table-wrap">
            ${renderTable()}
        </div>
    </div>`;
}

function renderTable() {
    let records = filterRecords();

    // Sort
    if (state.sortField) {
        records.sort((a, b) => {
            let valA = a[state.sortField] || "";
            let valB = b[state.sortField] || "";

            // Handle time fields sorting
            if (['start_time_actual', 'end_time_actual'].includes(state.sortField)) {
                valA = valA.toString();
                valB = valB.toString();
            }

            if (valA < valB) return state.sortOrder === "asc" ? -1 : 1;
            if (valA > valB) return state.sortOrder === "asc" ? 1 : -1;
            return 0;
        });
    }

    if (records.length === 0) {
        return `<div class="hc-no-results">${L.no_results}</div>`;
    }

    const sortIcon = (field) => {
        if (state.sortField !== field) return "";
        return state.sortOrder === "asc" ? " ↑" : " ↓";
    };

    const rows = records
        .map(
            (r, i) => {
                let diffHtml = "—";
                let diffs = [];
                if (r.start_time && r.start_time_actual) {
                    const diffMin = getMinutesDifference(r.start_time, r.start_time_actual);
                    if (diffMin > state.allowedLateDistribute) diffs.push(`<span class="hc-red">Đã trễ P ${diffMin}p</span>`);
                    else if (diffMin < -state.allowedEarlyDistribute) diffs.push(`<span class="hc-yellow">Sớm P ${Math.abs(diffMin)}p</span>`);
                }
                if (r.end_time && r.end_time_actual) {
                    const diffMin = getMinutesDifference(r.end_time, r.end_time_actual);
                    if (diffMin > state.allowedLateCollect) diffs.push(`<span class="hc-orange">Đã trễ T ${diffMin}p</span>`);
                }

                if (isRecordLateForDistribute(r)) {
                    diffs.push(`<span class="hc-red" style="font-weight:bold;">⏳ Đang trễ P ${getMinutesDifference(r.start_time, getProactiveNowTime())}p</span>`);
                }
                if (isRecordLateForCollect(r)) {
                    diffs.push(`<span class="hc-orange" style="font-weight:bold;">⏳ Đang trễ T ${getMinutesDifference(r.end_time, getProactiveNowTime())}p</span>`);
                }

                if (diffs.length > 0) {
                    diffHtml = diffs.join("<br>");
                } else if ((r.start_time && r.start_time_actual) || (r.end_time && r.end_time_actual)) {
                    diffHtml = `<span class="hc-green">Đúng giờ</span>`;
                }

                return `
        <tr class="hc-clickable-row ${i % 2 ? "hc-row-alt" : ""}" data-name="${r.name}" title="Double click để mở chi tiết">
            <td>${i + 1}</td>
            <td class="hc-mono">${r.hospital_code || ""}</td>
            <td class="hc-mono hc-dim">${r.employee || ""}</td>
            <td class="hc-bold">
                ${r.employee_name || ""}
                ${r.pregnant ? '<span class="hc-pregnant-badge">🤰</span>' : ""}
            </td>
            <td class="${r.gender === "Nữ" || r.gender === "Female" ? "hc-pink" : "hc-cyan"}">${r.gender || ""}</td>
            <td class="hc-dim">${r.custom_group || ""}</td>
            <td class="hc-mono">${formatTime(r.start_time)}</td>
            <td class="hc-mono ${r.start_time_actual ? "hc-green" : "hc-muted"}">${formatTime(r.start_time_actual)}</td>
            <td class="hc-center">${diffHtml}</td>
            <td class="hc-mono ${r.end_time_actual ? "hc-green" : "hc-muted"}">${formatTime(r.end_time_actual)}</td>
            <td>${statusBadge(r)}</td>
        </tr>`;
            }
        )
        .join("");

    return `
    <table class="hc-table">
        <thead>
            <tr>
                <th>${L.col_stt}</th>
                <th class="sortable" data-sort="hospital_code" style="cursor: pointer;">${L.col_code}${sortIcon("hospital_code")}</th>
                <th class="sortable" data-sort="employee" style="cursor: pointer;">${L.col_emp}${sortIcon("employee")}</th>
                <th class="sortable" data-sort="employee_name" style="cursor: pointer;">${L.col_name}${sortIcon("employee_name")}</th>
                <th class="sortable" data-sort="gender" style="cursor: pointer;">${L.col_gender}${sortIcon("gender")}</th>
                <th class="sortable" data-sort="custom_group" style="cursor: pointer;">${L.col_group}${sortIcon("custom_group")}</th>
                <th class="sortable" data-sort="start_time" style="cursor: pointer;">Giờ hẹn${sortIcon("start_time")}</th>
                <th class="sortable" data-sort="start_time_actual" style="cursor: pointer;">${L.col_dist}${sortIcon("start_time_actual")}</th>
                <th>${L.col_time_diff}</th>
                <th class="sortable" data-sort="end_time_actual" style="cursor: pointer;">${L.col_coll}${sortIcon("end_time_actual")}</th>
                <th>${L.col_status}</th>
            </tr>
        </thead>
        <tbody>${rows}</tbody>
    </table>
    <div class="hc-table-count" style="text-align: center;">
        Hiển thị ${records.length} / ${state.records.length} bản ghi
    </div>`;
}

function filterRecords() {
    let records = [...state.records];

    // Status filter
    if (state.statusFilter !== "all") {
        if (state.statusFilter === "late_dist") {
            records = records.filter(r => isRecordLateForDistribute(r));
        } else if (state.statusFilter === "late_coll") {
            records = records.filter(r => isRecordLateForCollect(r));
        } else {
            records = records.filter((r) => {
                const status = getStatus(r);
                return status === state.statusFilter;
            });
        }
    }

    // Search filter
    if (state.searchQuery) {
        const q = state.searchQuery.toLowerCase();
        records = records.filter(
            (r) =>
                (r.hospital_code || "").toLowerCase().includes(q) ||
                (r.employee || "").toLowerCase().includes(q) ||
                (r.employee_name || "").toLowerCase().includes(q) ||
                (r.custom_group || "").toLowerCase().includes(q)
        );
    }

    return records;
}

function setupListEvents() {
    // Search
    $("#list-search").on("input", function () {
        state.searchQuery = $(this).val();
        $("#hc-table-wrap").html(renderTable());
    });

    // Filter buttons
    $(document).off("click", ".hc-filter-btn").on("click", ".hc-filter-btn", function () {
        $(".hc-filter-btn").removeClass("active");
        $(this).addClass("active");
        state.statusFilter = $(this).data("filter");
        $("#hc-table-wrap").html(renderTable());
    });

    // Sort headers
    $(document).off("click", ".sortable").on("click", ".sortable", function () {
        const field = $(this).data("sort");
        if (state.sortField === field) {
            state.sortOrder = state.sortOrder === "asc" ? "desc" : "asc";
        } else {
            state.sortField = field;
            state.sortOrder = "asc";
        }
        $("#hc-table-wrap").html(renderTable());
    });

    // Double click row to open document
    $(document).off("dblclick", ".hc-clickable-row").on("dblclick", ".hc-clickable-row", function () {
        const docName = $(this).data("name");
        if (docName) {
            window.open(`/desk/health-check-up/${encodeURIComponent(docName)}`, '_blank');
        }
    });
}

// ============================================================
// Helpers
// ============================================================
function getMinutesDifference(timePlanned, timeActual) {
    const t1 = String(timePlanned).split(":");
    const t2 = String(timeActual).split(":");
    if (t1.length >= 2 && t2.length >= 2) {
        const h1 = parseInt(t1[0]), m1 = parseInt(t1[1]);
        const h2 = parseInt(t2[0]), m2 = parseInt(t2[1]);
        return (h2 * 60 + m2) - (h1 * 60 + m1);
    }
    return 0;
}

function getProactiveNowTime() {
    const today = frappe.datetime.get_today();
    if (state.currentDate === today) {
        return frappe.datetime.now_time();
    } else if (state.currentDate < today) {
        return "23:59:59";
    } else {
        return "00:00:00";
    }
}

function isRecordLateForDistribute(r) {
    if (r.start_time_actual) return false;
    if (!r.start_time) return false;
    const nowTime = getProactiveNowTime();
    return getMinutesDifference(r.start_time, nowTime) > state.allowedLateDistribute;
}

function isRecordLateForCollect(r) {
    if (!r.start_time_actual) return false;
    if (r.end_time_actual) return false;
    if (!r.end_time) return false;
    const nowTime = getProactiveNowTime();
    return getMinutesDifference(r.end_time, nowTime) > state.allowedLateCollect;
}
function getStatus(r) {
    if (r.end_time_actual) return "completed";
    if (r.start_time_actual) return "distributed";
    return "pending";
}

function statusBadge(r) {
    const status = getStatus(r);
    const map = {
        completed: { label: L.status_completed, cls: "hc-badge-green" },
        distributed: { label: L.status_distributed, cls: "hc-badge-yellow" },
        pending: { label: L.status_pending, cls: "hc-badge-red" },
    };
    const s = map[status];
    return `<span class="hc-badge ${s.cls}">${s.label}</span>`;
}

function formatTime(val) {
    if (!val) return "—";
    // Handle timedelta string "H:MM:SS" or "HH:MM:SS"
    const str = String(val);
    const parts = str.split(":");
    if (parts.length >= 2) {
        return parts[0].padStart(2, "0") + ":" + parts[1];
    }
    return str;
}

function showLoading() {
    $("#hc-content").html(
        `<div class="hc-loading">${L.loading}</div>`
    );
}

function updateDateDisplay() {
    // Left empty as we now use the native select dropdown
}

function startClock() {
    function update() {
        const now = new Date();
        const time =
            String(now.getHours()).padStart(2, "0") +
            ":" +
            String(now.getMinutes()).padStart(2, "0");
        $("#hc-clock").text(time);
    }
    update();
    setInterval(update, 30000);
}

// ============================================================
// Realtime
// ============================================================
function setupRealtime() {
    // Remove existing listener first
    frappe.realtime.off("health_check_update");

    // Force socket to join a dedicated room to guarantee delivery
    if (frappe.realtime.socket) {
        frappe.realtime.socket.emit("task_subscribe", "health_check_updates");
    }

    frappe.realtime.on("health_check_update", (data) => {
        console.log("Health Check Realtime Update Received:", data);
        if (data.date !== state.currentDate) return;

        // Update record in local state
        const idx = state.records.findIndex(
            (r) => r.name === data.record_name
        );
        if (idx === -1) return;

        if (data.action === "distribute") {
            state.records[idx].start_time_actual = data.start_time_actual;
            if (data.start_time) state.records[idx].start_time = data.start_time;
        } else if (data.action === "collect") {
            state.records[idx].end_time_actual = data.end_time_actual;
            if (data.start_time_actual) state.records[idx].start_time_actual = data.start_time_actual;
            if (data.end_time) state.records[idx].end_time = data.end_time;
            state.records[idx].x_ray = data.x_ray;
            state.records[idx].gynecological_exam =
                data.gynecological_exam;
        }

        // Recalculate stats
        recalculateStats();

        // Update mini bar (always in header, always needs update)
        renderMiniBar();

        // Targeted partial update per tab — avoids full re-render which breaks scan form focus
        switch (state.activeTab) {
            case "dashboard":
                // Refresh stat cards only, keep charts (expensive) as-is
                updateDashboardStats();
                break;
            case "distribute":
            case "collect":
                // Update only history list – do NOT reset the input form
                const mode = state.activeTab === "distribute" ? "distribute" : "collect";
                populateScanHistory(mode);
                renderHistory();
                break;
            case "list":
                // Re-render only the table tbody
                $("#hc-table-wrap").html(renderTable());
                break;
        }
    });
}

function recalculateStats() {
    const records = state.records;
    const total = records.length;
    const distributed = records.filter((r) => r.start_time_actual).length;
    const completed = records.filter((r) => r.end_time_actual).length;

    state.stats = {
        total,
        distributed,
        completed,
        in_exam: distributed - completed,
        not_started: total - distributed,
        x_ray: records.filter((r) => r.x_ray).length,
        gynecological_exam: records.filter((r) => r.gynecological_exam)
            .length,
        pregnant: records.filter((r) => r.pregnant).length,
    };

    // Recalculate groups
    const groups = {};
    const sections = {};
    records.forEach((r) => {
        const g = r.custom_group || "Không xác định";
        const s = r.custom_section || "Không xác định";

        if (!groups[g])
            groups[g] = { total: 0, distributed: 0, completed: 0 };
        groups[g].total++;
        if (r.start_time_actual) groups[g].distributed++;
        if (r.end_time_actual) groups[g].completed++;

        if (!sections[s])
            sections[s] = { total: 0, distributed: 0, completed: 0 };
        sections[s].total++;
        if (r.start_time_actual) sections[s].distributed++;
        if (r.end_time_actual) sections[s].completed++;
    });

    state.groups = Object.entries(groups)
        .map(([k, v]) => ({ group: k, ...v }))
        .sort((a, b) => a.group.localeCompare(b.group));

    state.sections = Object.entries(sections)
        .map(([k, v]) => ({ section: k, ...v }))
        .sort((a, b) => b.total - a.total);
}

function setupPollingAutoSync() {
    if (window.hcAutoSyncInterval) clearInterval(window.hcAutoSyncInterval);

    window.hcAutoSyncInterval = setInterval(() => {
        if (!state.currentDate) return;

        frappe.call({
            method: "customize_erpnext.health_check_up.api.health_check_api.get_health_check_data",
            args: { date: state.currentDate, hospital_code: null },
            callback: function (r) {
                if (r.message && r.message.records) {
                    const newRecords = r.message.records;

                    // Generate hashes to compare if states changed
                    const currHash = state.records.reduce((acc, rec) => acc + (rec.start_time_actual || "") + (rec.end_time_actual || ""), "");
                    const newHash = newRecords.reduce((acc, rec) => acc + (rec.start_time_actual || "") + (rec.end_time_actual || ""), "");

                    if (currHash !== newHash) {
                        console.log("Auto-Sync: Data naturally changed. Updating ui...");
                        state.records = newRecords;
                        recalculateStats();
                        renderMiniBar();

                        // Surgical DOM update mimicking real-time
                        switch (state.activeTab) {
                            case "dashboard":
                                updateDashboardStats();
                                break;
                            case "distribute":
                            case "collect":
                                const mode = state.activeTab === "distribute" ? "distribute" : "collect";
                                populateScanHistory(mode);
                                renderHistory();
                                break;
                            case "list":
                                renderListTable();
                                break;
                        }
                    }
                }
            }
        });
    }, 3000); // Sync every 3 seconds
}
