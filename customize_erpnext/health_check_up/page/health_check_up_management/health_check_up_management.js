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
    chart_by_start_time: "Tiến độ theo Giờ bắt đầu dự kiến",
    scan_placeholder: "Scan hoặc nhập mã hồ sơ / mã nhân viên...",
    btn_distribute: "Ghi nhận phát HS",
    btn_collect: "Ghi nhận thu HS",
    msg_success: "Thành công",
    msg_updated: "Đã cập nhật lại",
    msg_not_found: "Không tìm thấy",
    msg_input_required: "Vui lòng nhập mã hồ sơ hoặc mã nhân viên",
    msg_network_error: "Mất kết nối — scan đã lưu tạm, sẽ tự gửi khi có mạng",
    msg_server_error: "Lỗi server. Vui lòng thử lại.",
    msg_session_expired: "Phiên đăng nhập hết hạn, đang tải lại...",
    msg_retrying: "Mất kết nối, đang thử lại",
    msg_offline_queued: "scan đang chờ gửi",
    msg_queue_flushed: "Đã đồng bộ tất cả scan còn tồn.",
    col_stt: "#",
    col_code: "Mã HS",
    col_emp: "Mã NV",
    col_name: "Họ tên",
    col_gender: "Giới tính",
    col_group: "Group",
    col_dist: "Phát HS",
    col_coll: "Thu HS",
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
    settings_title: "Cấu hình thời gian",
    allowed_late_dist: "Phút khám trễ cho phép",
    allowed_late_coll: "Phút nộp HS trễ cho phép",
    allowed_early_dist: "Phút khám sớm cho phép",
    time_compare_mode: "Cách so sánh thời gian",
    time_compare_datetime: "Kết hợp date & time",
    time_compare_time_only: "Chỉ dựa vào time",
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
    timeCompareMode: "datetime", // 'datetime' or 'time_only'
    chartLayout: "vertical", // 'vertical' or 'horizontal'
    pollingInterval: 3, // seconds
    // Sort
    sortField: null,
    sortOrder: "asc",
    // Dashboard time range filter (for phát/thu stats)
    dashTimeFrom: "07:00",
    dashTimeTo: "17:00",
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
    page.add_inner_button("Hướng dẫn sử dụng", () => showGuideDialog());

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

    // Network online/offline handling
    window.addEventListener("online", onNetworkOnline);
    window.addEventListener("offline", onNetworkOffline);
    updateOfflineBanner();
    // Nếu vào trang khi đang online và có queue từ session trước → flush ngay
    if (navigator.onLine && getOfflineQueue().length > 0) {
        // Delay nhỏ để trang load xong trước
        setTimeout(() => flushOfflineQueue(), 2000);
    }
};

function showGuideDialog() {
    const d = new frappe.ui.Dialog({
        title: "Hướng dẫn sử dụng — Quản lý Khám Sức Khỏe",
        size: "extra-large",
    });

    $(d.body).html(`
    <style>
        .hc-guide { font-size: 14px; color: #334155; line-height: 1.7; padding: 4px 0; }
        .hc-guide h3 { font-size: 15px; font-weight: 700; color: #1e293b; margin: 20px 0 8px; padding-bottom: 6px; border-bottom: 2px solid #e2e8f0; }
        .hc-guide h3:first-child { margin-top: 0; }
        .hc-guide h4 { font-size: 13px; font-weight: 600; color: #4f46e5; margin: 14px 0 6px; }
        .hc-guide p { margin-bottom: 8px; color: #475569; }
        .hc-guide ul, .hc-guide ol { padding-left: 18px; margin-bottom: 8px; color: #475569; }
        .hc-guide li { margin-bottom: 4px; }
        .hc-guide code { font-family: monospace; font-size: 12px; background: #f1f5f9; border: 1px solid #e2e8f0; padding: 1px 5px; border-radius: 3px; color: #4f46e5; }
        .hc-guide strong { color: #1e293b; }
        .hc-guide .hg-badge { display: inline-block; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 10px; }
        .hc-guide .hg-green { background: #d1fae5; color: #065f46; }
        .hc-guide .hg-yellow { background: #fef3c7; color: #92400e; }
        .hc-guide .hg-gray { background: #f1f5f9; color: #475569; }
        .hc-guide .hg-alert { background: #eff6ff; border: 1px solid #bfdbfe; border-left: 4px solid #3b82f6; border-radius: 6px; padding: 8px 12px; margin: 10px 0; color: #1e40af; font-size: 13px; }
        .hc-guide .hg-warn { background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 8px 12px; margin: 10px 0; color: #92400e; font-size: 13px; }
        .hg-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
        .hg-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 12px; }
        .hg-card b { display: block; font-size: 13px; color: #1e293b; margin-bottom: 4px; }
        .hg-card span { font-size: 12px; color: #64748b; }
        .hg-table { width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }
        .hg-table th, .hg-table td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }
        .hg-table th { background: #f8fafc; font-weight: 600; color: #334155; }
        .hg-steps { counter-reset: s; list-style: none; padding: 0; }
        .hg-steps li { counter-increment: s; display: flex; gap: 10px; align-items: flex-start; margin-bottom: 8px; }
        .hg-steps li::before { content: counter(s); flex-shrink: 0; width: 22px; height: 22px; border-radius: 50%; background: #4f46e5; color: #fff; font-size: 11px; font-weight: 700; display: flex; align-items: center; justify-content: center; margin-top: 2px; }
    </style>
    <div class="hc-guide">

        <h3>📋 Giới thiệu</h3>
        <p>Phần mềm hỗ trợ phát hành và thu nhận hồ sơ khám sức khỏe qua quét mã vạch, theo dõi tiến độ theo thời gian thực.</p>
        <div class="hg-alert">Dữ liệu tập trung tại DocType <code>Health Check-Up</code>. Truy cập: <code>/desk/health-check-up-management</code></div>

        <h3>🗂️ 4 Tab chính</h3>
        <div class="hg-grid">
            <div class="hg-card"><b>📊 Tổng Quan</b><span>Stat cards tiến độ, biểu đồ Section/Group/Giờ hẹn</span></div>
            <div class="hg-card"><b>📥 Phát Hồ Sơ</b><span>Ghi nhận thời điểm NV đến lấy hồ sơ</span></div>
            <div class="hg-card"><b>📤 Thu Hồ Sơ</b><span>Ghi nhận thời điểm NV nộp lại hồ sơ, ghi X-Quang / Phụ khoa</span></div>
            <div class="hg-card"><b>📋 Danh Sách NV</b><span>Xem trạng thái từng NV, tìm kiếm, lọc, xuất Excel</span></div>
        </div>
        <div class="hg-warn">Tab Phát HS / Thu HS bị khóa nếu ngày được chọn là <strong>ngày trong quá khứ</strong>.</div>

        <h3>📥 Phát Hồ Sơ</h3>
        <ol class="hg-steps">
            <li><span>Bấm tab <strong>Phát Hồ Sơ</strong>.</span></li>
            <li><span>Quét mã vạch hoặc gõ <strong>4 số cuối</strong> mã NV.</span></li>
            <li><span>Hệ thống hiển thị tên & nhóm NV trên nút xác nhận xanh.</span></li>
            <li><span>(Tùy chọn) Nhập ghi chú nếu cần.</span></li>
            <li><span>Bấm nút hoặc nhấn <code>Enter</code> để lưu.</span></li>
        </ol>
        <div class="hg-alert">Nếu hồ sơ đã phát trước đó, hệ thống hỏi xác nhận trước khi ghi đè.</div>

        <h3>📤 Thu Hồ Sơ</h3>
        <ol class="hg-steps">
            <li><span>Bấm tab <strong>Thu Hồ Sơ</strong>.</span></li>
            <li><span>Quét mã vạch hoặc gõ 4 số cuối mã NV.</span></li>
            <li><span>Tích vào ô <strong>X-Quang</strong> / <strong>Phụ Khoa</strong> nếu hồ sơ có. <em>(Tự động tích Phụ khoa cho NV nữ.)</em></span></li>
            <li><span>Bấm <strong>Ghi nhận</strong> để hoàn tất.</span></li>
        </ol>
        <div class="hg-warn">Nếu hồ sơ <strong>chưa được phát</strong>, hệ thống yêu cầu nhập giờ phát thủ công.</div>

        <h3>📊 Dashboard Tổng quan</h3>
        <h4>Nhóm thẻ thống kê</h4>
        <div class="hg-grid">
            <div class="hg-card">
                <b>Tiến độ chung</b>
                <span>👥 Tổng hồ sơ (cố định) · 📤 Đã phát HS · 🔄 Đang khám · ✅ Hoàn thành · 🔬 X-Quang · 👩‍⚕️ Phụ khoa</span>
            </div>
            <div class="hg-card">
                <b>Thông tin thêm</b>
                <span>👨 Nam · 👩 Nữ · 🤰 Mang thai · ⏰ Trễ giờ phát · ⏳ Trễ giờ thu · ❌ Chưa khám</span>
            </div>
        </div>
        <p>Click vào thẻ → mở danh sách NV thuộc nhóm đó.</p>

        <h4>Bộ lọc Dashboard</h4>
        <ul>
            <li><strong>Giờ bắt đầu / Section / Group</strong> — lọc theo lịch hẹn & phòng ban.</li>
            <li><strong>Thời gian thu / phát HS</strong> — lọc theo giờ phát/thu thực tế (mặc định 07:00–17:00). Record chưa có actual time luôn được giữ.</li>
        </ul>

        <h3>🏷️ Trạng thái Hồ Sơ</h3>
        <table class="hg-table">
            <thead><tr><th>Trạng thái</th><th>Điều kiện</th></tr></thead>
            <tbody>
                <tr><td><span class="hg-badge hg-gray">Chưa khám</span></td><td>Chưa có giờ phát thực tế</td></tr>
                <tr><td><span class="hg-badge hg-yellow">Đang khám</span></td><td>Có giờ phát, chưa có giờ thu</td></tr>
                <tr><td><span class="hg-badge hg-green">Hoàn thành</span></td><td>Có cả giờ phát và giờ thu</td></tr>
            </tbody>
        </table>

        <h3>📡 Mất kết nối mạng</h3>
        <p>Scan vẫn được <strong>lưu tạm</strong> khi mất mạng. Khi có mạng trở lại, hệ thống tự động gửi lại toàn bộ.</p>

        <h3>🔧 Admin (IT)</h3>
        <p>Vào List View của <code>Health Check-Up</code> → menu góc phải:</p>
        <table class="hg-table">
            <thead><tr><th>Chức năng</th><th>Mô tả</th></tr></thead>
            <tbody>
                <tr><td><strong>Recalculate Status</strong></td><td>Tính lại Status hàng loạt theo ngày</td></tr>
                <tr><td><strong>Clear Actual Data</strong></td><td>Xóa giờ phát/thu theo ngày (reset đợt khám)</td></tr>
                <tr><td><strong>Change Date</strong></td><td>Chuyển toàn bộ dữ liệu từ ngày A sang ngày B</td></tr>
            </tbody>
        </table>

    </div>`);

    d.show();
}

function downloadExcel() {
    if (!state.records || state.records.length === 0) {
        frappe.msgprint("Không có dữ liệu để tải xuống.");
        return;
    }

    window.open(`/api/method/customize_erpnext.health_check_up.api.health_check_api.get_excel_data?date=${state.currentDate}`);
}

frappe.pages["health-check-up-management"].on_page_show = function () {
    // Re-subscribe realtime when returning to page (also fires on first load)
    setupRealtime();
    setupPollingAutoSync();
    updateOfflineBanner();
};

frappe.pages["health-check-up-management"].on_page_hide = function () {
    stopCameraScanner();
    // Unsubscribe to avoid memory leaks
    frappe.realtime.off("health_check_update");
    if (window.hcAutoSyncInterval) clearInterval(window.hcAutoSyncInterval);
    window.removeEventListener("online", onNetworkOnline);
    window.removeEventListener("offline", onNetworkOffline);
};

// ============================================================
// Layout Builder
// ============================================================
function buildLayout() {
    return `
    <div class="hc-app">
        <!-- Offline Banner -->
        <div id="hc-offline-banner" class="hc-offline-banner" style="display:none;">
            <span id="hc-offline-icon">📡</span>
            <span id="hc-offline-text">Mất kết nối mạng</span>
            <span id="hc-offline-queue-count"></span>
        </div>
        <!-- Header Bar -->
        <div class="hc-header">
            <div class="hc-header-left">
                <div id="hc-dash-filters-wrap" style="display:none;"></div>
                <span class="hc-sync-status" id="hc-sync-status"></span>
            </div>
            <div class="hc-tabs" id="hc-tabs">
                <select class="hc-date-select" id="hc-date-select" style="margin-right: 8px;"></select>
                <button class="hc-tab active" data-tab="dashboard">${L.tab_dashboard}</button>
                <button class="hc-tab" data-tab="distribute">${L.tab_distribute} <span class="hc-tab-count" id="tab-count-distribute"></span></button>
                <button class="hc-tab" data-tab="collect">${L.tab_collect} <span class="hc-tab-count" id="tab-count-collect"></span></button>
                <button class="hc-tab" data-tab="list">${L.tab_list}</button>
            </div>
        </div>

        <!-- Content Area -->
        <div class="hc-content" id="hc-content">
            <div class="hc-loading" id="hc-loading">${L.loading}</div>
        </div>
    </div>`;
}

function updateTabCounts() {
    const total = state.stats.total || 0;
    const distributed = state.stats.distributed || 0;
    const completed = state.stats.completed || 0;
    $("#tab-count-distribute").text(total > 0 ? `${distributed}/${total}` : "");
    $("#tab-count-collect").text(total > 0 ? `${completed}/${total}` : "");
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
            state.currentDate = r.message.date;

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
    recalculateStats();
    updateTabCounts();
    renderActiveTab();
}

// ============================================================
// Tab Navigation
// ============================================================
function setupTabNavigation() {
    $(document).on("click", ".hc-tab", function () {
        stopCameraScanner();
        if (!$(this).hasClass("active") && $(this).data("tab") !== "dashboard") {
            $("#hc-dash-filters-wrap").hide();
        }
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


function renderActiveTab() {
    const $content = $("#hc-content");
    switch (state.activeTab) {
        case "dashboard":
            $content.html(renderDashboard());
            renderDashboardFilters();
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
function renderDashboardFilters() {
    const startTimes = [...new Set(state.records.map(r => formatTime(r.start_time)).filter(t => t !== "—"))].sort();
    const sectionList = [...new Set(state.records.map(r => r.custom_section).filter(Boolean))].sort();
    const groupList = [...new Set(state.records.map(r => r.custom_group).filter(Boolean))].sort();

    $("#hc-dash-filters-wrap").html(`
        <div class="hc-dash-filter-item">
            <label class="hc-dash-filter-label">Giờ bắt đầu</label>
            <select class="hc-dash-filter-select" id="dash-filter-time">
                <option value="all">Tất cả</option>
                ${startTimes.map(t => `<option value="${t}" ${state.dashFilterStartTime === t ? 'selected' : ''}>${t}</option>`).join('')}
            </select>
        </div>
        <div class="hc-dash-filter-item">
            <label class="hc-dash-filter-label">Section</label>
            <select class="hc-dash-filter-select" id="dash-filter-section">
                <option value="all">Tất cả</option>
                ${sectionList.map(s => `<option value="${s}" ${state.dashFilterSection === s ? 'selected' : ''}>${s}</option>`).join('')}
            </select>
        </div>
        <div class="hc-dash-filter-item">
            <label class="hc-dash-filter-label">Group</label>
            <select class="hc-dash-filter-select" id="dash-filter-group">
                <option value="all">Tất cả</option>
                ${groupList.map(g => `<option value="${g}" ${state.dashFilterGroup === g ? 'selected' : ''}>${g}</option>`).join('')}
            </select>
        </div>
        <div class="hc-dash-filter-item hc-dash-filter-time-range">
            <label class="hc-dash-filter-label">Thời gian phát / thu HS</label>
            <div style="display:flex; align-items:center; gap:4px;">
                <div id="dash-time-from-wrap"></div>
                <span style="font-size:11px; color:var(--text-muted);">–</span>
                <div id="dash-time-to-wrap"></div>
            </div>
        </div>
        <button class="hc-dash-filter-reset" id="dash-filter-reset" title="Đặt lại bộ lọc">↺ Đặt lại</button>
        <button class="hc-config-btn" id="dash-settings-btn" title="Cấu hình">Cấu hình</button>
    `).css("display", "flex");
}

function renderDashboard() {
    // Apply dashboard filters
    const filtered = getDashboardFilteredRecords();
    const s = calcFilteredStats(filtered);

    return `
    <div class="hc-dashboard">
        <!-- Stat Cards -->
        <div id="hc-stats-wrapper">
            <div class="hc-stats-group-title">Tiến độ chung</div>
            <div class="hc-stats-grid mb-3">
                ${statCard("total", L.stat_total, state.records.length, null, "cyan", "👥")}
                ${statCard("distributed", L.stat_distributed, s.distributed, s.total, "blue", "📤")}
                ${statCard("in_exam", L.stat_in_exam, s.in_exam, s.total, "yellow", "🔄")}
                ${statCard("completed", L.stat_completed, s.completed, s.total, "green", "✅")}
                ${statCard("x_ray", L.stat_xray, s.x_ray, s.total, "cyan", "🔬")}
                ${statCard("gynecological_exam", L.stat_gynec, s.gynecological_exam, s.total, "purple", "👩‍⚕️")}
            </div>

            <div class="hc-stats-group-title">Thông tin thêm</div>
            <div class="hc-stats-grid mb-3">
                ${statCard("male", "Nam", s.male, s.total, "blue", "👨")}
                ${statCard("female", "Nữ", s.female, s.total, "pink", "👩")}
                ${statCard("pregnant", L.stat_pregnant, s.pregnant, s.total, "purple", "🤰")}
                ${statCard("late_dist", L.stat_late_dist, s.late_dist, s.total, "red", "⏰", s.late_dist > 0)}
                ${statCard("late_coll", L.stat_late_coll, s.late_coll, s.total, "orange", "⏳", s.late_coll > 0)}
                ${statCard("not_started", L.stat_not_started, s.not_started, s.total, "red", "❌")}
            </div>
        </div>

        <!-- Charts -->
        <div class="hc-charts-stack">
            <div class="hc-chart-card">
                <div class="hc-chart-title">${L.chart_by_start_time}</div>
                <div id="chart-start-time"></div>
            </div>
            <div class="hc-charts-row">
                <div class="hc-chart-card">
                    <div class="hc-chart-title">${L.chart_by_group}</div>
                    <div id="chart-group"></div>
                </div>
                <div class="hc-chart-card">
                    <div class="hc-chart-title">${L.chart_by_section}</div>
                    <div id="chart-section"></div>
                </div>
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

    // Filter by actual time range:
    // - Chưa có actual time nào → luôn giữ lại (Chưa khám)
    // - Có actual time → giữ nếu start_time_actual HOẶC end_time_actual nằm trong khoảng
    if (state.dashTimeFrom || state.dashTimeTo) {
        const pad = t => t ? String(t).split(":").slice(0, 2).map(x => x.padStart(2, "0")).join(":") : null;
        const from = pad(state.dashTimeFrom);
        const to = pad(state.dashTimeTo);
        const inRange = t => {
            const tp = pad(t);
            if (!tp) return false;
            if (from && tp < from) return false;
            if (to && tp > to) return false;
            return true;
        };
        records = records.filter(r => {
            if (!r.start_time_actual && !r.end_time_actual) return true;
            return inRange(r.start_time_actual) || inRange(r.end_time_actual);
        });
    }

    return records;
}

function calcFilteredStats(records) {
    const total = records.length;
    const completed = records.filter(r => r.status === "Hoàn thành").length;
    const in_exam_count = records.filter(r => r.status === "Đang khám").length;
    const distributed = completed + in_exam_count;

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
        in_exam: in_exam_count,
        not_started: records.filter(r => r.status === "Chưa khám").length,
        x_ray: records.filter(r => r.x_ray).length,
        gynecological_exam: records.filter(r => r.gynecological_exam).length,
        pregnant: records.filter(r => r.pregnant).length,
        male: records.filter(r => r.gender === "Nam" || r.gender === "Male").length,
        female: records.filter(r => r.gender === "Nữ" || r.gender === "Female").length,
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
        <div class="hc-stats-group-title">Tiến độ chung</div>
        <div class="hc-stats-grid mb-3">
            ${statCard("total", L.stat_total, state.records.length, null, "cyan", "👥")}
            ${statCard("distributed", L.stat_distributed, s.distributed, s.total, "blue", "📤")}
            ${statCard("in_exam", L.stat_in_exam, s.in_exam, s.total, "yellow", "🔄")}
            ${statCard("completed", L.stat_completed, s.completed, s.total, "green", "✅")}
            ${statCard("x_ray", L.stat_xray, s.x_ray, s.total, "cyan", "🔬")}
            ${statCard("gynecological_exam", L.stat_gynec, s.gynecological_exam, s.total, "purple", "👩‍⚕️")}
        </div>

        <div class="hc-stats-group-title">Thông tin thêm</div>
        <div class="hc-stats-grid mb-3">
            ${statCard("male", "Nam", s.male, s.total, "blue", "👨")}
            ${statCard("female", "Nữ", s.female, s.total, "pink", "👩")}
            ${statCard("pregnant", L.stat_pregnant, s.pregnant, s.total, "purple", "🤰")}
            ${statCard("late_dist", L.stat_late_dist, s.late_dist, s.total, "red", "⏰", s.late_dist > 0)}
            ${statCard("late_coll", L.stat_late_coll, s.late_coll, s.total, "orange", "⏳", s.late_coll > 0)}
            ${statCard("not_started", L.stat_not_started, s.not_started, s.total, "red", "❌")}
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
    // Frappe Time controls for khoảng giờ TT
    const ctrlFrom = frappe.ui.form.make_control({
        parent: document.getElementById("dash-time-from-wrap"),
        df: { fieldtype: "Time", fieldname: "dash_time_from", label: "", placeholder: "Từ giờ" },
        render_input: true,
    });
    ctrlFrom.set_value(state.dashTimeFrom + ":00");
    ctrlFrom.$input.on("change blur", function () {
        const val = ctrlFrom.get_value();
        if (val) { state.dashTimeFrom = val.slice(0, 5); updateDashboardStats(); }
    });

    const ctrlTo = frappe.ui.form.make_control({
        parent: document.getElementById("dash-time-to-wrap"),
        df: { fieldtype: "Time", fieldname: "dash_time_to", label: "", placeholder: "Đến giờ" },
        render_input: true,
    });
    ctrlTo.set_value(state.dashTimeTo + ":00");
    ctrlTo.$input.on("change blur", function () {
        const val = ctrlTo.get_value();
        if (val) { state.dashTimeTo = val.slice(0, 5); updateDashboardStats(); }
    });
    $("#dash-filter-reset").on("click", function () {
        state.dashFilterStartTime = "all";
        state.dashFilterSection = "all";
        state.dashFilterGroup = "all";
        state.dashTimeFrom = "07:00";
        state.dashTimeTo = "17:00";
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
            },
            {
                fieldtype: "Select",
                fieldname: "time_compare_mode",
                label: L.time_compare_mode,
                options: `${L.time_compare_datetime}\n${L.time_compare_time_only}`,
                default: state.timeCompareMode === "datetime" ? L.time_compare_datetime : L.time_compare_time_only,
            },
            {
                fieldtype: "Select",
                fieldname: "chart_layout",
                label: "Hướng biểu đồ",
                options: "Dọc\nNgang",
                default: state.chartLayout === "vertical" ? "Dọc" : "Ngang",
            },
            {
                fieldtype: "Int",
                fieldname: "polling_interval",
                label: "Polling interval (giây)",
                default: state.pollingInterval,
                description: "Tần suất tự động đồng bộ dữ liệu. Mặc định: 3 giây.",
            },
        ],
        primary_action_label: L.btn_save,
        primary_action(values) {
            state.allowedLateDistribute = values.allowed_late_dist;
            state.allowedLateCollect = values.allowed_late_coll;
            state.allowedEarlyDistribute = values.allowed_early_dist;
            state.timeCompareMode = values.time_compare_mode === L.time_compare_datetime ? "datetime" : "time_only";
            state.chartLayout = values.chart_layout === "Dọc" ? "vertical" : "horizontal";
            const newInterval = Math.max(1, parseInt(values.polling_interval) || 3);
            if (newInterval !== state.pollingInterval) {
                state.pollingInterval = newInterval;
                setupPollingAutoSync(); // restart với interval mới
            }
            renderActiveTab();
            dialog.hide();
        },
    });

    dialog.add_custom_button(L.btn_reset, () => {
        dialog.set_values({
            allowed_late_dist: 10,
            allowed_late_coll: 0,
            allowed_early_dist: 10,
            time_compare_mode: L.time_compare_datetime,
            chart_layout: "Dọc",
            polling_interval: 3,
        });
    });

    dialog.show();
}

function getStatModalData(type) {
    const filtered = getDashboardFilteredRecords();
    switch (type) {
        case "total": return filtered;
        case "distributed": return filtered.filter(r => r.status !== "Chưa khám");
        case "completed": return filtered.filter(r => r.status === "Hoàn thành");
        case "in_exam": return filtered.filter(r => r.status === "Đang khám");
        case "not_started": return filtered.filter(r => r.status === "Chưa khám");
        case "late_dist":
            return filtered.filter(r => isRecordLateForDistribute(r));
        case "late_coll":
            return filtered.filter(r => isRecordLateForCollect(r));
        case "pregnant": return filtered.filter(r => r.pregnant);
        case "x_ray": return filtered.filter(r => r.x_ray);
        case "gynecological_exam": return filtered.filter(r => r.gynecological_exam);
        case "male": return filtered.filter(r => r.gender === "Nam" || r.gender === "Male");
        case "female": return filtered.filter(r => r.gender === "Nữ" || r.gender === "Female");
        default: return [];
    }
}

function showStatModal(type) {
    const records = getStatModalData(type);

    const cols = [
        { label: "Mã HS", field: "hospital_code", cls: "hc-mono" },
        { label: "Mã NV", field: "employee", cls: "hc-mono" },
        { label: "Họ tên", field: "employee_name", cls: "hc-bold" },
        { label: "Group", field: "custom_group", cls: "" },
        { label: "Phát (DK)", field: "start_time", cls: "hc-mono" },
        { label: "Thu (DK)", field: "end_time", cls: "hc-mono" },
        { label: "Phát (TT)", field: "start_time_actual", cls: "hc-mono" },
        { label: "Thu (TT)", field: "end_time_actual", cls: "hc-mono" },
        { label: "Ghi chú", field: "note", cls: "" },
    ];

    let sortField = null;
    let sortOrder = "asc";

    const TIME_FIELDS = ["start_time", "end_time", "start_time_actual", "end_time_actual"];

    function sortedRecords() {
        if (!sortField) return records;
        return [...records].sort((a, b) => {
            let va = a[sortField] || "";
            let vb = b[sortField] || "";
            if (TIME_FIELDS.includes(sortField)) {
                va = formatTime(va);
                vb = formatTime(vb);
            } else {
                va = String(va);
                vb = String(vb);
            }
            if (va < vb) return sortOrder === "asc" ? -1 : 1;
            if (va > vb) return sortOrder === "asc" ? 1 : -1;
            return 0;
        });
    }

    function renderThead() {
        return `<thead style="position: sticky; top: 0; background: var(--bg-color); z-index: 1;">
            <tr>
                <th style="cursor:default;">#</th>
                ${cols.map(c => {
            const icon = sortField === c.field ? (sortOrder === "asc" ? " ↑" : " ↓") : "";
            return `<th class="hc-stat-modal-th" data-field="${c.field}" style="cursor:pointer; user-select:none;">${c.label}${icon}</th>`;
        }).join("")}
            </tr>
        </thead>`;
    }

    function renderTbody() {
        const rows = sortedRecords();
        if (rows.length === 0) {
            return `<tbody><tr><td colspan="${cols.length + 1}" class="text-center text-muted">Không có dữ liệu</td></tr></tbody>`;
        }
        return `<tbody>${rows.map((r, i) => `
            <tr class="${i % 2 ? 'hc-row-alt' : ''}">
                <td>${i + 1}</td>
                <td class="hc-mono">${r.hospital_code || ""}</td>
                <td class="hc-mono">${r.employee || ""}</td>
                <td class="hc-bold">${r.employee_name || ""}</td>
                <td>${r.custom_group || ""}</td>
                <td class="hc-mono">${formatTime(r.start_time)}</td>
                <td class="hc-mono">${formatTime(r.end_time)}</td>
                <td class="hc-mono ${r.start_time_actual ? 'hc-green' : 'hc-muted'}">${formatTime(r.start_time_actual)}</td>
                <td class="hc-mono ${r.end_time_actual ? 'hc-green' : 'hc-muted'}">${formatTime(r.end_time_actual)}</td>
                <td style="max-width:200px; white-space:normal;">${r.note || ""}</td>
            </tr>`).join("")}
        </tbody>`;
    }

    function renderTable() {
        return `<div style="max-height:420px; overflow-y:auto; overflow-x:auto;">
            <table class="table table-bordered hc-stat-modal-table" style="font-size:11px;" id="stat-modal-table">
                ${renderThead()}
                ${renderTbody()}
            </table>
        </div>`;
    }

    const dialog = new frappe.ui.Dialog({
        title: `Danh sách nhân viên (${records.length})`,
        size: "extra-large",
    });

    $(dialog.body).html(renderTable());

    $(dialog.body).on("click", ".hc-stat-modal-th", function () {
        const field = $(this).data("field");
        if (sortField === field) {
            sortOrder = sortOrder === "asc" ? "desc" : "asc";
        } else {
            sortField = field;
            sortOrder = "asc";
        }
        $("#stat-modal-table thead").replaceWith(renderThead());
        $("#stat-modal-table tbody").replaceWith(renderTbody());
    });

    dialog.show();
}

function statCard(type, label, value, total, color, icon, isAlert = false) {
    const pct =
        total != null && total > 0
            ? Math.round((value / total) * 100) + "%"
            : "";
    const alertClass = isAlert ? " hc-stat-alert" : "";
    return `
    <div class="hc-stat-card hc-stat-${color} clickable-card${alertClass}" data-type="${type}" style="cursor: pointer;">
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
            <span class="hc-hchart-legend-item"><span class="hc-hchart-legend-color hc-bg-none"></span> ${L.stat_not_started}</span>
        </div>
    </div>`;
    document.getElementById(containerId).innerHTML = html;
}

function getHcColor(name, fallback) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function renderCharts() {
    const filtered = getDashboardFilteredRecords();
    const groups = {};
    const sections = {};
    filtered.forEach((r) => {
        const g = r.custom_group || "Không xác định";
        const s = r.custom_section || "Không xác định";
        if (!groups[g]) groups[g] = { total: 0, distributed: 0, completed: 0 };
        groups[g].total++;
        if (r.status !== "Chưa khám") groups[g].distributed++;
        if (r.status === "Hoàn thành") groups[g].completed++;
        if (!sections[s]) sections[s] = { total: 0, distributed: 0, completed: 0 };
        sections[s].total++;
        if (r.status !== "Chưa khám") sections[s].distributed++;
        if (r.status === "Hoàn thành") sections[s].completed++;
    });
    const startTimes = {};
    filtered.forEach((r) => {
        const t = formatTime(r.start_time);
        const key = (t && t !== "—") ? t : "Không xác định";
        if (!startTimes[key]) startTimes[key] = { total: 0, distributed: 0, completed: 0 };
        startTimes[key].total++;
        if (r.status !== "Chưa khám") startTimes[key].distributed++;
        if (r.status === "Hoàn thành") startTimes[key].completed++;
    });
    const startTimeArr = Object.entries(startTimes).map(([k, v]) => ({ slot: k, ...v })).sort((a, b) => a.slot.localeCompare(b.slot));

    const groupArr = Object.entries(groups).map(([k, v]) => ({ group: k, ...v })).sort((a, b) => a.group.localeCompare(b.group));
    const sectionArr = Object.entries(sections).map(([k, v]) => ({ section: k, ...v })).sort((a, b) => b.total - a.total);
    const colors = [getHcColor('--hc-green', '#10b981'), getHcColor('--hc-yellow', '#f59e0b'), getHcColor('--hc-red', '#ef4444')];

    if (startTimeArr.length > 0) {
        if (state.chartLayout === "horizontal") {
            renderHorizontalChart("chart-start-time", startTimeArr, "slot");
        } else if (typeof frappe.Chart !== "undefined") {
            const labels = startTimeArr.map((s) => `${s.slot} (${s.total})`);
            new frappe.Chart("#chart-start-time", {
                data: {
                    labels, datasets: [
                        { name: L.stat_completed, values: startTimeArr.map((s) => s.completed) },
                        { name: L.stat_in_exam, values: startTimeArr.map((s) => s.distributed - s.completed) },
                        { name: L.stat_not_started, values: startTimeArr.map((s) => s.total - s.distributed) },
                    ]
                },
                type: "bar", height: 300, colors,
                barOptions: { stacked: true, spaceRatio: 0.4 },
            });
            setTimeout(() => {
                document.querySelectorAll("#chart-start-time .x.axis .tick text").forEach((el, idx) => {
                    if (labels[idx]) el.textContent = labels[idx];
                    el.setAttribute("text-anchor", "end");
                    el.style.transformBox = "fill-box";
                    el.style.transformOrigin = "right center";
                    el.style.transform = "rotate(-45deg)";
                });
            }, 500);
        }
    }

    if (sectionArr.length > 0) {
        if (state.chartLayout === "horizontal") {
            renderHorizontalChart("chart-section", sectionArr, "section");
        } else if (typeof frappe.Chart !== "undefined") {
            const labels = sectionArr.map((s) => `${s.section} (${s.total})`);
            new frappe.Chart("#chart-section", {
                data: {
                    labels, datasets: [
                        { name: L.stat_completed, values: sectionArr.map((s) => s.completed) },
                        { name: L.stat_in_exam, values: sectionArr.map((s) => s.distributed - s.completed) },
                        { name: L.stat_not_started, values: sectionArr.map((s) => s.total - s.distributed) },
                    ]
                },
                type: "bar", height: 300, colors,
                barOptions: { stacked: true, spaceRatio: 0.4 },
            });
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

    if (groupArr.length > 0) {
        if (state.chartLayout === "horizontal") {
            renderHorizontalChart("chart-group", groupArr, "group");
        } else if (typeof frappe.Chart !== "undefined") {
            const labels = groupArr.map((g) => `${g.group} (${g.total})`);
            new frappe.Chart("#chart-group", {
                data: {
                    labels, datasets: [
                        { name: L.stat_completed, values: groupArr.map((g) => g.completed) },
                        { name: L.stat_in_exam, values: groupArr.map((g) => g.distributed - g.completed) },
                        { name: L.stat_not_started, values: groupArr.map((g) => g.total - g.distributed) },
                    ]
                },
                type: "bar", height: 300, colors,
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
function renderCollectMiniStats() {
    return `
        <span class="hc-mini-stat-item hc-mini-stat-cyan">🔬 ${L.stat_xray}: <strong>${state.stats.x_ray || 0}</strong></span>
        <span class="hc-mini-stat-item hc-mini-stat-purple">👩‍⚕️ ${L.stat_gynec}: <strong>${state.stats.gynecological_exam || 0}</strong></span>
    `;
}

function renderScanForm(mode) {
    const isDist = mode === "distribute";
    return `
    <div class="hc-scan-layout">
        <div class="hc-scan-card">
            <h2 class="hc-scan-title">
                ${isDist ? L.tab_distribute : L.tab_collect}
            </h2>
            ${!isDist ? `
            <div class="hc-collect-mini-stats" id="collect-mini-stats">
                ${renderCollectMiniStats()}
            </div>` : ''}
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

            <div class="hc-input-group" id="scan-input-group">
                <span class="hc-input-prefix" id="scan-prefix" style="display:none;">TIQN-</span>
                <input type="text" class="hc-scan-input" id="scan-input"
                       placeholder="${L.scan_placeholder}" autocomplete="off" />
                <button class="hc-camera-btn" id="scan-camera-btn" title="Quét mã bằng camera">📷 Camera</button>
            </div>
            <div id="hc-qr-reader" style="display:none; margin: 8px 0; border-radius: 8px; overflow: hidden;"></div>

            ${!isDist
            ? `
            <div class="hc-scan-checkboxes" id="scan-checkboxes">
                <label class="hc-checkbox-label" id="lbl-xray">
                    <input type="checkbox" id="chk-xray" checked />
                    <span>${L.stat_xray}</span>
                </label>
                <label class="hc-checkbox-label" id="lbl-gynec">
                    <input type="checkbox" id="chk-gynec" />
                    <span>${L.stat_gynec}</span>
                </label>
            </div>`
            : ""
        }

            <div class="hc-note-toggle-wrap">
                <button class="hc-note-toggle-btn" id="note-toggle-btn" type="button">+ Ghi chú</button>
                <textarea class="hc-scan-note" id="scan-note"
                          placeholder="Ghi chú thêm (không bắt buộc)" rows="2"
                          style="resize: none;"></textarea>
            </div>

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
    const $btn = $("#scan-btn");

    populateScanHistory(mode);

    const defaultBtnText = mode === "distribute" ? L.btn_distribute : L.btn_collect;

    // Live Preview & Auto check checkboxes on input change
    $input.on("input", function () {
        const code = $(this).val().trim();
        const scanType = $(`input[name="scan_type_${mode}"]:checked`).val();
        let record = null;

        if (code) {
            if (scanType === "employee" && /^\d{4}$/.test(code)) {
                // Strictly 4 digits only
                record = state.records.find(r => r.employee && r.employee.endsWith(code));
            } else if (scanType === "hospital") {
                record = state.records.find(r => r.hospital_code === code);
            }
        }

        // 1. Update Submit Button Text (Live Preview)
        if (record) {
            const groupText = record.custom_group ? ` - ${record.custom_group}` : "";
            const pregnantTag = (mode === "collect" && record.pregnant) ? " 🤰" : "";
            $btn.text(`Ghi nhận: ${record.employee_name}${groupText}${pregnantTag}`);
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

    // Update input UI and trigger preview when scan type changes
    function applyScanType() {
        const scanType = $(`input[name="scan_type_${mode}"]:checked`).val();
        if (scanType === "employee") {
            $("#scan-prefix").show();
            $input.attr("maxlength", 4).attr("placeholder", "4 số cuối mã NV").attr("inputmode", "numeric");
            $("#scan-input-group").addClass("hc-input-group--employee");
        } else {
            $("#scan-prefix").hide();
            $input.removeAttr("maxlength").attr("placeholder", L.scan_placeholder).removeAttr("inputmode");
            $("#scan-input-group").removeClass("hc-input-group--employee");
        }
        $input.val("").trigger("input").focus();
    }

    $(`input[name="scan_type_${mode}"]`).on("change", applyScanType);
    applyScanType();
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

    // Camera button
    $("#scan-camera-btn").on("click", function () {
        if (hcQrScanner) {
            stopCameraScanner();
        } else {
            startCameraScanner(mode);
        }
    });

    // Collapsible note toggle (mobile only — CSS controls visibility on desktop)
    $("#note-toggle-btn").on("click", function () {
        const $note = $("#scan-note");
        const isOpen = $note.hasClass("hc-note-visible");
        if (isOpen) {
            $note.removeClass("hc-note-visible").blur();
            $(this).text("+ Ghi chú");
        } else {
            $note.addClass("hc-note-visible").focus();
            $(this).text("- Ẩn ghi chú");
        }
    });

    // Auto-scroll submit button into view when keyboard opens on mobile
    $input.on("focus", function () {
        setTimeout(function () {
            const $btn = $("#scan-btn");
            if ($btn.length) {
                $btn[0].scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
        }, 400);
    });
}

function populateScanHistory(mode) {
    const timeField = mode === "distribute" ? "start_time_actual" : "end_time_actual";

    // Filter records that have the timeField set
    const scanned = state.records.filter(r => r[timeField]);

    // Sort descending by time — use formatTime to pad hours (e.g. "9:30" → "09:30") so string compare works correctly
    scanned.sort((a, b) => {
        const ta = formatTime(a[timeField]);
        const tb = formatTime(b[timeField]);
        if (ta < tb) return 1;
        if (ta > tb) return -1;
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
        if (!/^\d{4}$/.test(code)) {
            showScanResult("error", "Mã nhân viên phải là đúng 4 chữ số (4 ký tự cuối mã NV).");
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

    const executeCall = async (retryCount = 0) => {
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

                // Update local state immediately (don't wait for realtime)
                if (rec) {
                    const idx = state.records.findIndex(r => r.name === rec.name);
                    if (idx !== -1) {
                        if (mode === "distribute") {
                            state.records[idx].start_time_actual = rec.start_time_actual;
                        } else if (mode === "collect") {
                            state.records[idx].end_time_actual = rec.end_time_actual;
                            state.records[idx].x_ray = rec.x_ray;
                            state.records[idx].gynecological_exam = rec.gynecological_exam;
                        }
                        if (rec.status) state.records[idx].status = rec.status;
                        if (rec.note !== undefined) state.records[idx].note = rec.note;
                    }
                    recalculateStats();
                    updateTabCounts();
                    if (mode === "collect") {
                        $("#collect-mini-stats").html(renderCollectMiniStats());
                    }
                }

                // Reset form only on success
                $input.val("").trigger("input").focus();
                $note.val("");
                if (mode === "collect") {
                    $("#chk-xray").prop("checked", true);
                    $("#lbl-gynec").show();
                    $("#chk-gynec").prop("checked", false);
                }
            }
        } catch (e) {
            if (isNetworkError(e)) {
                if (retryCount < 2) {
                    // Auto-retry tối đa 2 lần
                    showScanResult("warning", `${L.msg_retrying} (${retryCount + 1}/2)...`);
                    await new Promise(res => setTimeout(res, 1200));
                    return executeCall(retryCount + 1);
                }
                // Vẫn lỗi → queue lại
                enqueueOfflineScan(mode, args);
                showScanResult("error", L.msg_network_error);
                $input.val("").trigger("input").focus();
                $note.val("");
            } else if (e.httpStatus === 403 || (e.message && e.message.includes("403"))) {
                showScanResult("error", L.msg_session_expired);
                setTimeout(() => location.reload(), 2000);
            } else {
                // Server error (frappe.throw, 500, v.v.)
                showScanResult("error", e.message || L.msg_server_error);
                $input.focus();
            }
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
        // Allow pressing Enter to confirm
        d.$wrapper.on("keydown.confirm_dialog", function (e) {
            if (e.key === "Enter") {
                e.preventDefault();
                d.$wrapper.find(".btn-primary").click();
            }
        });
    } else {
        executeCall();
    }
}

function showScanResult(type, message, record) {
    const colors = {
        success: "green",
        update: "yellow",
        warning: "orange",
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
                <span style="color: var(--hc-text-light); min-width: 70px;">${h.xray ? 'X-Quang' : ''}</span>
                <span style="color: var(--hc-text-light); min-width: 75px;">${h.gynec ? 'Phụ khoa' : ''}</span>
            ` : ''}
            <span style="color: var(--hc-yellow); font-style: italic; overflow: hidden; text-overflow: ellipsis; flex: 1;">${h.note || ''}</span>
            <span class="hc-history-mode" style="font-weight: 600; min-width: 30px; text-align: right;">${h.mode === "distribute" ? "Phát" : "Thu"}</span>
        </div>`
        )
        .join("");
    $list.html(html);
}

// ============================================================
// Offline Queue & Network Error Handling
// ============================================================
const HC_OFFLINE_QUEUE_KEY = "hc_offline_scan_queue";

function isNetworkError(e) {
    if (!navigator.onLine) return true;
    if (e instanceof TypeError && /fetch|Failed to fetch|NetworkError/i.test(e.message)) return true;
    return false;
}

function getOfflineQueue() {
    try { return JSON.parse(localStorage.getItem(HC_OFFLINE_QUEUE_KEY) || "[]"); } catch { return []; }
}

function saveOfflineQueue(queue) {
    localStorage.setItem(HC_OFFLINE_QUEUE_KEY, JSON.stringify(queue));
}

function enqueueOfflineScan(mode, args) {
    const queue = getOfflineQueue();
    queue.push({ mode, args, timestamp: new Date().toISOString(), date: state.currentDate });
    saveOfflineQueue(queue);
    updateOfflineBanner();
}

function updateOfflineBanner() {
    const queue = getOfflineQueue();
    const isOffline = !navigator.onLine;
    const $banner = $("#hc-offline-banner");
    if (!$banner.length) return;

    if (isOffline || queue.length > 0) {
        $banner.show();
        if (isOffline) {
            $banner.removeClass("hc-offline-banner--online");
            $("#hc-offline-icon").text("📡");
            $("#hc-offline-text").text("Mất kết nối mạng");
        } else {
            $banner.addClass("hc-offline-banner--online");
            $("#hc-offline-icon").text("✅");
            $("#hc-offline-text").text("Đã kết nối —");
        }
        $("#hc-offline-queue-count").text(
            queue.length > 0 ? `${queue.length} ${L.msg_offline_queued}` : ""
        );
    } else {
        $banner.hide();
    }
}

async function flushOfflineQueue() {
    const queue = getOfflineQueue();
    if (queue.length === 0) return;

    updateOfflineBanner(); // show "đang đồng bộ"
    const failed = [];
    for (const item of queue) {
        try {
            const method = item.mode === "distribute"
                ? `${API_BASE}.scan_distribute`
                : `${API_BASE}.scan_collect`;
            const r = await frappe.call({ method, args: item.args });
            if (r.message && r.message.success) {
                const rec = r.message.record;
                if (rec) {
                    const idx = state.records.findIndex(s => s.name === rec.name);
                    if (idx !== -1) {
                        if (item.mode === "distribute") {
                            state.records[idx].start_time_actual = rec.start_time_actual;
                        } else {
                            state.records[idx].end_time_actual = rec.end_time_actual;
                            state.records[idx].x_ray = rec.x_ray;
                            state.records[idx].gynecological_exam = rec.gynecological_exam;
                        }
                        if (rec.status) state.records[idx].status = rec.status;
                    }
                    addToHistory(rec, item.mode, "success");
                }
            }
        } catch (e) {
            if (isNetworkError(e)) {
                failed.push(item); // giữ lại để retry sau
            }
            // Server error: bỏ qua, không retry
        }
    }

    saveOfflineQueue(failed);
    recalculateStats();
    updateTabCounts();
    updateOfflineBanner();

    if (failed.length === 0 && queue.length > 0) {
        frappe.show_alert({ message: L.msg_queue_flushed, indicator: "green" }, 3);
    }
}

function onNetworkOnline() {
    updateOfflineBanner();
    flushOfflineQueue();
}

function onNetworkOffline() {
    updateOfflineBanner();
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

            // Handle time fields sorting — pad hours via formatTime so "9:30" sorts correctly vs "11:00"
            if (['start_time_actual', 'end_time_actual', 'start_time', 'end_time'].includes(state.sortField)) {
                valA = formatTime(valA);
                valB = formatTime(valB);
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
                    const diffMin = getMinutesDiffByMode(r.start_time, r.start_time_actual, state.currentDate, state.currentDate);
                    if (diffMin > state.allowedLateDistribute) diffs.push(`<span class="hc-red">Đã trễ P ${diffMin}p</span>`);
                    else if (diffMin < -state.allowedEarlyDistribute) diffs.push(`<span class="hc-yellow">Sớm P ${Math.abs(diffMin)}p</span>`);
                }
                if (r.end_time && r.end_time_actual) {
                    const diffMin = getMinutesDiffByMode(r.end_time, r.end_time_actual, state.currentDate, state.currentDate);
                    if (diffMin > state.allowedLateCollect) diffs.push(`<span class="hc-orange">Đã trễ T ${diffMin}p</span>`);
                }

                const now = getProactiveNow();
                const lateDistMin = getMinutesDiffByMode(r.start_time, now.time, state.currentDate, now.date);
                const isLateDist = !r.start_time_actual && r.start_time && lateDistMin > state.allowedLateDistribute;
                if (isLateDist) {
                    diffs.push(`<span class="hc-red" style="font-weight:bold;">Đang trễ P ${lateDistMin}p</span>`);
                }
                const lateCollMin = getMinutesDiffByMode(r.end_time, now.time, state.currentDate, now.date);
                const isLateColl = r.start_time_actual && !r.end_time_actual && r.end_time && lateCollMin > state.allowedLateCollect;
                if (isLateColl) {
                    diffs.push(`<span class="hc-orange" style="font-weight:bold;">Đang trễ T ${lateCollMin}p</span>`);
                }

                if (diffs.length > 0) {
                    diffHtml = diffs.join("<br>");
                } else if ((r.start_time && r.start_time_actual) || (r.end_time && r.end_time_actual)) {
                    diffHtml = `<span class="hc-green">Đúng giờ</span>`;
                }

                const rowClass = [
                    "hc-clickable-row",
                    i % 2 ? "hc-row-alt" : "",
                    isLateDist ? "hc-row-late-dist" : "",
                    isLateColl ? "hc-row-late-coll" : "",
                ].filter(Boolean).join(" ");

                return `
        <tr class="${rowClass}" data-name="${r.name}" title="Double click để mở chi tiết">
            <td>${i + 1}</td>
            <td class="hc-mono">${r.hospital_code || ""}</td>
            <td class="hc-mono hc-dim">${r.employee || ""}</td>
            <td class="hc-bold">
                ${r.employee_name || ""}
                ${r.pregnant ? ' 🤰' : ""}
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
        } else if (state.statusFilter === "distributed") {
            // "Đã phát HS" = tất cả có status !== "Chưa khám" (bao gồm cả Hoàn thành)
            records = records.filter(r => r.status !== "Chưa khám");
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

// Returns minutes difference using full datetime (date + time) comparison
function getMinutesDiffDatetime(datePlanned, timePlanned, dateActual, timeActual) {
    const pad = s => String(s).split(":").slice(0, 2).map(x => x.padStart(2, "0")).join(":");
    const dt1 = new Date(`${datePlanned}T${pad(timePlanned)}:00`);
    const dt2 = new Date(`${dateActual}T${pad(timeActual)}:00`);
    if (isNaN(dt1.getTime()) || isNaN(dt2.getTime())) return 0;
    return Math.round((dt2 - dt1) / 60000);
}

// Returns {date, time} of "now" for the active mode
function getProactiveNow() {
    const today = frappe.datetime.get_today();
    const nowTime = frappe.datetime.now_time();
    if (state.timeCompareMode === "datetime") {
        // datetime mode: use actual system time; future dates are never late
        if (state.currentDate > today) return { date: state.currentDate, time: "00:00:00" };
        return { date: today, time: nowTime };
    } else {
        // time_only mode: legacy proactive logic (only time matters)
        if (state.currentDate === today) return { date: today, time: nowTime };
        if (state.currentDate < today) return { date: state.currentDate, time: "23:59:59" };
        return { date: state.currentDate, time: "00:00:00" };
    }
}

// Minutes difference honoring state.timeCompareMode
// datePlanned / dateActual are optional; default to state.currentDate for both
function getMinutesDiffByMode(timePlanned, timeActual, datePlanned, dateActual) {
    if (state.timeCompareMode === "datetime") {
        return getMinutesDiffDatetime(
            datePlanned || state.currentDate,
            timePlanned,
            dateActual || state.currentDate,
            timeActual
        );
    }
    return getMinutesDifference(timePlanned, timeActual);
}

function isRecordLateForDistribute(r) {
    if (r.start_time_actual) return false;
    if (!r.start_time) return false;
    const now = getProactiveNow();
    return getMinutesDiffByMode(r.start_time, now.time, state.currentDate, now.date) > state.allowedLateDistribute;
}

function isRecordLateForCollect(r) {
    if (!r.start_time_actual) return false;
    if (r.end_time_actual) return false;
    if (!r.end_time) return false;
    const now = getProactiveNow();
    return getMinutesDiffByMode(r.end_time, now.time, state.currentDate, now.date) > state.allowedLateCollect;
}
function getStatus(r) {
    if (r.status === "Hoàn thành") return "completed";
    if (r.status === "Đang khám") return "distributed";
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
            state.records[idx].gynecological_exam = data.gynecological_exam;
        }
        if (data.status) state.records[idx].status = data.status;

        // Recalculate stats
        recalculateStats();
        updateTabCounts();

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
                if (state.activeTab === "collect") {
                    $("#collect-mini-stats").html(renderCollectMiniStats());
                }
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
    const completed = records.filter((r) => r.status === "Hoàn thành").length;
    const in_exam = records.filter((r) => r.status === "Đang khám").length;
    const distributed = completed + in_exam;

    state.stats = {
        total,
        distributed,
        completed,
        in_exam,
        not_started: records.filter((r) => r.status === "Chưa khám").length,
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
        if (r.status !== "Chưa khám") groups[g].distributed++;
        if (r.status === "Hoàn thành") groups[g].completed++;

        if (!sections[s])
            sections[s] = { total: 0, distributed: 0, completed: 0 };
        sections[s].total++;
        if (r.status !== "Chưa khám") sections[s].distributed++;
        if (r.status === "Hoàn thành") sections[s].completed++;
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

                    // Update last-sync timestamp
                    const nowStr = frappe.datetime.now_time().slice(0, 5);
                    $("#hc-sync-status").attr("data-synced", "1").attr("title", `Đồng bộ lúc ${nowStr}`).text(nowStr);

                    if (currHash !== newHash) {
                        state.records = newRecords;
                        recalculateStats();
                        updateTabCounts();

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
                                if (state.activeTab === "collect") {
                                    $("#collect-mini-stats").html(renderCollectMiniStats());
                                }
                                break;
                            case "list":
                                $("#hc-table-wrap").html(renderTable());
                                break;
                        }
                    }
                }
            }
        });
    }, state.pollingInterval * 1000);
}

// ============================================================
// Camera / Barcode Scanner
// ============================================================
let hcQrScanner = null;
let hcQrLibLoaded = false;

function loadQrLib(callback) {
    if (hcQrLibLoaded) { callback(); return; }
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js';
    script.onload = () => { hcQrLibLoaded = true; callback(); };
    script.onerror = () => frappe.show_alert({ message: 'Không tải được thư viện camera.', indicator: 'red' });
    document.head.appendChild(script);
}

function playScanBeep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = 1200;
        gain.gain.setValueAtTime(0.3, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
        osc.start();
        osc.stop(ctx.currentTime + 0.15);
    } catch (e) { }
}

function scanHaptic() {
    if (navigator.vibrate) navigator.vibrate(120);
}

function startCameraScanner(mode) {
    loadQrLib(() => {
        const $reader = $('#hc-qr-reader');
        const $btn = $('#scan-camera-btn');

        if (hcQrScanner) {
            try { hcQrScanner.clear(); } catch (e) { }
            hcQrScanner = null;
        }

        $reader.html('<div class="hc-scan-line-wrap"><div class="hc-scan-line"></div></div>').show();
        $btn.text('Dừng camera');

        let lastScanned = '';
        let scanCooldown = false;

        // Responsive qrbox: 85% viewport width, tối đa 400px, cao 80px cho 1D barcode
        const qrboxWidth = Math.min(Math.floor(window.innerWidth * 0.85), 400);

        hcQrScanner = new Html5Qrcode('hc-qr-reader', {
            formatsToSupport: [
                Html5QrcodeSupportedFormats.CODE_39,
                Html5QrcodeSupportedFormats.CODE_128,
                Html5QrcodeSupportedFormats.QR_CODE
            ],
            verbose: false
        });

        hcQrScanner.start(
            { facingMode: 'environment' },
            { fps: 15, qrbox: { width: qrboxWidth, height: 80 } },
            (decodedText) => {
                // Strip Code 39 start/stop * markers, normalize whitespace
                const cleanText = decodedText.trim().replace(/^\*+|\*+$/g, '').trim();
                if (!cleanText) return;
                if (scanCooldown || cleanText === lastScanned) return;

                lastScanned = cleanText;
                scanCooldown = true;

                playScanBeep();
                scanHaptic();

                $('#scan-input').val(cleanText).trigger('input');
                doScan(mode);

                // Sau 2.5 giây: reset để sẵn sàng scan mã tiếp theo
                setTimeout(() => {
                    scanCooldown = false;
                    lastScanned = '';
                }, 2500);
            },
            () => { } // per-frame errors — bỏ qua
        ).catch(err => {
            frappe.show_alert({ message: 'Không mở được camera: ' + err, indicator: 'red' });
            $reader.hide();
            $btn.text('📷 Camera');
        });
    });
}

function stopCameraScanner() {
    if (hcQrScanner) {
        hcQrScanner.stop().catch(() => { });
        hcQrScanner.clear().catch(() => { });
        hcQrScanner = null;
    }
    $('#hc-qr-reader').hide();
    $('#scan-camera-btn').text('📷 Camera');
}
