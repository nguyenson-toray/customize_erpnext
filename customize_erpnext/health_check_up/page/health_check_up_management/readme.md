# Health Check Up Management — Tài liệu kỹ thuật

## Tổng quan

Trang quản lý khám sức khỏe nhân viên. Gồm 2 file chính:
- **Frontend**: `health_check_up_management.js`
- **Backend**: `../../api/health_check_api.py`
- **Hướng dẫn người dùng**: `document_for_user.md` (popup trong trang)

---

## Kiến trúc

```
[Frappe Page]
    └── on_page_load()
            ├── buildLayout()         → render HTML khung trang (bao gồm offline banner)
            ├── loadDates()           → lấy danh sách ngày có dữ liệu
            ├── loadData(date)        → lấy toàn bộ record + stats
            ├── setupTabNavigation()  → gắn event tab
            └── (network listeners)   → online/offline events

    └── on_page_show()                ← fires EVERY time page becomes visible (kể cả lần đầu)
            ├── setupRealtime()       → lắng nghe Socket.IO
            ├── setupPollingAutoSync()→ fallback polling (configurable, mặc định 3 giây)
            └── updateOfflineBanner() → hiển thị banner nếu có queue tồn đọng
```

> **Lưu ý**: `setupRealtime()` và `setupPollingAutoSync()` chỉ đặt trong `on_page_show` (không trùng lặp ở `on_page_load`) vì `on_page_show` cũng fire lần đầu.

---

## State (trạng thái toàn cục)

```javascript
state = {
    currentDate,           // ngày đang xem (YYYY-MM-DD)
    dates,                 // danh sách ngày có dữ liệu
    records,               // mảng toàn bộ record ngày hiện tại (unfiltered)
    stats,                 // { total, distributed, completed, in_exam, not_started, x_ray, gynecological_exam, pregnant, male, female }
    groups,                // breakdown theo custom_group (tính bởi recalculateStats)
    sections,              // breakdown theo custom_section (tính bởi recalculateStats)
    activeTab,             // 'dashboard' | 'distribute' | 'collect' | 'list'
    searchQuery,           // chuỗi tìm kiếm tab danh sách
    statusFilter,          // filter trạng thái tab danh sách
    scanHistory,           // lịch sử scan (top 50)
    dashFilterStartTime,   // filter giờ hẹn trên dashboard
    dashFilterSection,     // filter section trên dashboard
    dashFilterGroup,       // filter group trên dashboard
    dashTimeFrom,          // khoảng giờ TT từ (mặc định "07:00")
    dashTimeTo,            // khoảng giờ TT đến (mặc định "17:00")
    allowedLateDistribute, // ngưỡng trễ phát HS (phút)
    allowedLateCollect,    // ngưỡng trễ thu HS (phút)
    allowedEarlyDistribute,// ngưỡng sớm phát HS (phút)
    timeCompareMode,       // 'datetime' | 'time_only'
    chartLayout,           // 'vertical' | 'horizontal'
    pollingInterval,       // giây giữa các lần polling (mặc định 3)
    sortField,             // cột đang sort
    sortOrder,             // 'asc' | 'desc'
}
```

> `state.records` luôn là toàn bộ dữ liệu ngày hiện tại — dùng `getDashboardFilteredRecords()` để lấy bản đã filter cho dashboard.

---

## 4 Tabs

| Tab | ID | Chức năng |
|---|---|---|
| Tổng quan | `dashboard` | Stat cards 2 nhóm + biểu đồ Section/Group/Giờ hẹn |
| Phát Hồ Sơ | `distribute` | Scan phát hồ sơ, ghi `start_time_actual`. Badge hiển thị `đã phát / tổng` |
| Thu Hồ Sơ | `collect` | Scan thu hồ sơ, ghi `end_time_actual`. Badge hiển thị `đã thu / tổng` |
| Danh Sách NV | `list` | Bảng toàn bộ NV, search/filter/sort, export Excel |

> Tab Phát/Thu bị **disable** nếu ngày được chọn là ngày trong quá khứ.

---

## Dashboard — Stat Cards

Chia thành 2 nhóm:

| Nhóm | Cards |
|---|---|
| Tiến độ chung | Tổng hồ sơ (fixed), Đã phát HS, Đang khám, Hoàn thành, X-Quang, Phụ khoa |
| Thông tin thêm | Nam, Nữ, Mang thai, Trễ giờ phát HS, Trễ giờ thu HS, Chưa khám |

**Tổng hồ sơ**: dùng `state.records.length` — không bị ảnh hưởng bởi bộ lọc.

Click vào bất kỳ card nào → mở modal danh sách NV thuộc nhóm đó.

### Modal stat card
- Có sort theo tất cả cột
- Cột time sort dùng `formatTime()` để pad giờ — tránh lỗi `"9:xx" > "11:xx"`
- Có cột **Ghi chú** (`note`)

---

## Dashboard — Bộ lọc

```
getDashboardFilteredRecords() áp dụng lần lượt:
  1. dashFilterStartTime  → lọc theo formatTime(start_time)
  2. dashFilterSection    → lọc theo custom_section
  3. dashFilterGroup      → lọc theo custom_group
  4. dashTimeFrom/dashTimeTo → lọc theo start_time_actual hoặc end_time_actual
     Logic: record không có actual time nào → luôn giữ (Chưa khám)
            record có actual time → giữ nếu ít nhất 1 trong khoảng
```

Bộ lọc `dashTimeFrom`/`dashTimeTo` dùng Frappe Time control (`frappe.ui.form.make_control`) khởi tạo trong `setupDashboardFilters()`.

---

## Trạng thái record (`status` field)

Field `status` (Select) trên DocType tự động tính khi save qua `HealthCheckUp.compute_status()`:

```
Chưa khám  → start_time_actual = null
Đang khám  → start_time_actual có giá trị, end_time_actual = null
Hoàn thành → end_time_actual có giá trị
```

`getStatus(r)` ở client dùng `r.status` để map sang `'pending' | 'distributed' | 'completed'`.

---

## Biểu đồ (Charts)

3 biểu đồ tiến độ: theo Giờ bắt đầu, theo Group, theo Section.

- Label trục X hiển thị tổng số: `"08:00 (25)"`, `"Nhóm A (18)"`
- Hỗ trợ 2 hướng: **vertical** (Frappe Chart stacked bar) và **horizontal** (custom bar)
- Dữ liệu biểu đồ dựa trên `getDashboardFilteredRecords()` — có áp dụng bộ lọc

---

## Luồng dữ liệu chính

### 1. Khởi tải
```
loadDates() → render dropdown ngày
    → loadData(date) → gọi API get_health_check_data
        → state.records / stats
        → recalculateStats() → state.groups / sections
        → updateTabCounts()
        → renderActiveTab()
```

### 2. Scan phát hồ sơ (distribute)
```
doScan('distribute')
    → executeCall() → API scan_distribute(hospital_code/employee, date, note)
    → cập nhật state.records[idx]: start_time_actual + status
    → recalculateStats() + updateTabCounts()
```

### 3. Scan thu hồ sơ (collect)
```
doScan('collect')
    → nếu chưa phát → dialog nhập giờ phát thủ công
    → executeCall() → API scan_collect(hospital_code/employee, date, x_ray, gynec, note, manual_start_time)
    → cập nhật state.records[idx]: end_time_actual + x_ray + gynec + status
    → recalculateStats() + updateTabCounts()
```

### 4. Realtime sync
```
Backend publish 'health_check_update' (Socket.IO, sau commit)
    → setupRealtime() → cập nhật record trong state.records
    → cập nhật status từ data.status
    → recalculateStats() + partial update UI theo activeTab
Fallback: setupPollingAutoSync() → state.pollingInterval giây/lần
```

---

## Xử lý lỗi mạng (Offline Queue)

```
executeCall() → network error → auto-retry 2 lần → enqueueOfflineScan() → localStorage
window 'online' → flushOfflineQueue() → gửi lại → cập nhật state + status
```

| Lỗi | Xử lý |
|-----|-------|
| Network error | Retry 2 lần → queue localStorage |
| HTTP 403 | Thông báo → reload sau 2s |
| Server error (500, frappe.throw) | Hiện thông báo, giữ input |

localStorage key: `"hc_offline_scan_queue"` → `[{mode, args, timestamp, date}, ...]`

---

## Backend API — `health_check_api.py`

### API công khai (whitelist)

| Hàm | Mô tả |
|---|---|
| `get_health_check_dates()` | Danh sách ngày có dữ liệu (desc) |
| `get_health_check_data(date)` | Records + stats (dùng field `status` để đếm) |
| `scan_distribute(...)` | Phát HS: ghi `start_time_actual`, save → compute_status |
| `scan_collect(...)` | Thu HS: ghi `end_time_actual`, save → compute_status |
| `lookup_record(code, date)` | Tìm record theo mã HS hoặc mã NV |
| `get_excel_data(date)` | Xuất Excel (dùng column `status` thay vì SQL IF) |
| `recalculate_status_by_date(date)` | Bulk recalc status cho tất cả record theo ngày |
| `clear_actual_data(date)` | Xóa actual times theo ngày (admin) |
| `change_date(from_date, to_date)` | Chuyển date toàn bộ records (admin) |

### `get_health_check_data` — stats counting
Stats đếm dựa trên field `status`:
```python
completed = sum(1 for r in records if r.status == "Hoàn thành")
in_exam   = sum(1 for r in records if r.status == "Đang khám")
distributed = completed + in_exam
not_started = sum(1 for r in records if r.status == "Chưa khám")
```

### `_serialize_record` — fields trả về
Bao gồm `status` (thêm trong cuộc hội thoại 2026-03-30).

### `_publish_update` — realtime payload
Bao gồm `status` để client update trực tiếp không cần tính lại.

---

## DocType Controller — `health_check_up.py`

### `compute_status()`
Tự động tính field `status` mỗi khi `validate()` chạy:
```python
if self.end_time_actual:   self.status = "Hoàn thành"
elif self.start_time_actual: self.status = "Đang khám"
else:                       self.status = "Chưa khám"
```

---

## List View — `health_check_up_list.js`

Các menu item (IT only, cần mật khẩu):

| Menu | API | Mô tả |
|---|---|---|
| Recalculate Status | `recalculate_status_by_date` | Tính lại status hàng loạt theo ngày |
| Clear Actual Data | `clear_actual_data` | Xóa actual times theo ngày |
| Change Date | `change_date` | Chuyển ngày toàn bộ records |

---

## Frontend — Các hàm quan trọng

### Dashboard

| Hàm | Mô tả |
|---|---|
| `renderDashboard()` | Render stat cards 2 nhóm + biểu đồ |
| `getDashboardFilteredRecords()` | Filter theo start_time/section/group + khoảng giờ TT |
| `calcFilteredStats(records)` | Tính stats từ records đã filter (dùng r.status) |
| `updateDashboardStats()` | Cập nhật cards mà không re-render toàn bộ |
| `showStatModal(type)` | Mở modal danh sách NV theo loại stat |
| `renderCharts()` | Vẽ biểu đồ (dùng r.status để đếm distributed/completed) |
| `showGuideDialog()` | Mở popup hướng dẫn sử dụng (frappe.ui.Dialog) |

### Scan Form

| Hàm | Mô tả |
|---|---|
| `doScan(mode)` | Submit: validate → confirm → API → cập nhật state (gồm status) |
| `showScanResult(type, msg, record)` | Hiển thị kết quả. type: success/update/warning/error |
| `populateScanHistory(mode)` | Lọc và sort lịch sử từ state.records |

### Danh sách NV

| Hàm | Mô tả |
|---|---|
| `renderTable()` | Bảng có sort, count, double-click mở doctype |
| `filterRecords()` | Lọc theo statusFilter + searchQuery |
| `getStatus(r)` | Dùng `r.status` → 'completed' / 'distributed' / 'pending' |
| `statusBadge(r)` | Render badge màu dựa trên getStatus(r) |

### Tiện ích

| Hàm | Mô tả |
|---|---|
| `recalculateStats()` | Tính lại state.stats + groups + sections (dùng r.status) |
| `formatTime(val)` | timedelta string → `HH:MM` (có pad zero) hoặc `"—"` |

---

## Cấu hình (dialog "Cấu hình" trên Dashboard)

| Tùy chọn | State key | Mặc định |
|---|---|---|
| Phút khám trễ cho phép | `allowedLateDistribute` | 10 |
| Phút nộp HS trễ cho phép | `allowedLateCollect` | 0 |
| Phút khám sớm cho phép | `allowedEarlyDistribute` | 10 |
| Cách so sánh thời gian | `timeCompareMode` | datetime |
| Hướng biểu đồ | `chartLayout` | vertical |
| Polling interval (giây) | `pollingInterval` | 3 |

---

## Fields của một Record

```
name, hospital_code, employee, employee_name, gender
department, custom_section, custom_group, designation
health_check_type, pregnant (bool)
start_time, end_time         (giờ hẹn)
start_time_actual            (thực tế phát — null nếu chưa phát)
end_time_actual              (thực tế thu — null nếu chưa thu)
status                       (Chưa khám | Đang khám | Hoàn thành — auto-computed)
x_ray, gynecological_exam    (bool)
note, modified
```

---

## Debug nhanh

| Vấn đề | Kiểm tra |
|---|---|
| Stats không khớp | `recalculateStats()` dùng `r.status`; `calcFilteredStats()` cho dashboard (có thể khác) |
| Realtime không hoạt động | Kiểm tra `setupPollingAutoSync()` fallback (3s); room: `task_progress:health_check_updates` |
| Status sai | Chạy "Recalculate Status" từ List View → menu Admin |
| Khoảng giờ TT không lọc đúng | Logic: `!actual_time` → giữ lại; có actual time → lọc theo khoảng |
| Tab Phát/Thu bị disable | `loadData()` so sánh date với today |
| Export Excel lỗi | `downloadExcel()` mở `/api/method/...get_excel_data?date=...` |
| Sort thời gian sai thứ tự | Dùng `formatTime()` trước khi sort chuỗi (pad "9:xx" → "09:xx") |

---

## File liên quan

```
health_check_up/
├── page/health_check_up_management/
│   ├── health_check_up_management.js   ← Frontend chính
│   ├── health_check_up_management.css  ← Style
│   ├── health_check_up_management.html ← Template rỗng
│   ├── health_check_up_management.json ← Metadata page, roles
│   ├── document_for_user.md            ← Nội dung hướng dẫn người dùng
│   └── readme.md                       ← File này
├── api/
│   └── health_check_api.py             ← Backend API
├── doctype/health_check_up/
│   ├── health_check_up.py              ← Controller (compute_status)
│   ├── health_check_up_list.js         ← List view (admin menu items)
│   └── health_check_up.json            ← DocType definition (field status)
└── public/health_check_guide.html      ← Static guide page (dự phòng)
```
