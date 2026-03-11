# Health Check Up Management — Tài liệu kỹ thuật

## Tổng quan

Trang quản lý khám sức khỏe nhân viên. Gồm 2 file chính:
- **Frontend**: `health_check_up_management.js` (~1580 dòng)
- **Backend**: `../../api/health_check_api.py` (~550 dòng)

---

## Kiến trúc

```
[Frappe Page]
    └── on_page_load()
            ├── buildLayout()         → render HTML khung trang
            ├── loadDates()           → lấy danh sách ngày có dữ liệu
            ├── loadData(date)        → lấy toàn bộ record + stats
            ├── setupTabNavigation()  → gắn event tab
            ├── setupRealtime()       → lắng nghe Socket.IO
            ├── setupPollingAutoSync()→ fallback polling 3 giây
            └── startClock()         → đồng hồ header
```

---

## State (trạng thái toàn cục)

```javascript
state = {
    currentDate,          // ngày đang xem (YYYY-MM-DD)
    dates,                // danh sách ngày có dữ liệu
    records,              // mảng toàn bộ record ngày hiện tại
    stats,                // { total, distributed, completed, in_exam, not_started, x_ray, gynecological_exam, pregnant }
    groups,               // breakdown theo custom_group
    sections,             // breakdown theo custom_section
    activeTab,            // 'dashboard' | 'distribute' | 'collect' | 'list'
    searchQuery,          // chuỗi tìm kiếm tab danh sách
    statusFilter,         // filter trạng thái tab danh sách
    scanHistory,          // lịch sử scan (top 50)
    dashFilterStartTime,  // filter giờ hẹn trên dashboard
    dashFilterSection,    // filter section trên dashboard
    dashFilterGroup,      // filter group trên dashboard
    allowedLateDistribute,// ngưỡng trễ phát HS (phút)
    allowedLateCollect,   // ngưỡng trễ thu HS (phút)
    allowedEarlyDistribute,// ngưỡng sớm phát HS (phút)
    chartLayout,          // 'vertical' | 'horizontal'
    sortField,            // cột đang sort
    sortOrder,            // 'asc' | 'desc'
}
```

---

## 4 Tabs

| Tab | ID | Chức năng |
|---|---|---|
| Tổng quan | `dashboard` | Stat cards + biểu đồ Section/Group |
| Phát Hồ Sơ | `distribute` | Scan phát hồ sơ, ghi `start_time_actual` |
| Thu Hồ Sơ | `collect` | Scan thu hồ sơ, ghi `end_time_actual` |
| Danh Sách NV | `list` | Bảng toàn bộ NV, search/filter/sort, export Excel |

> **Lưu ý**: Tab Phát/Thu bị **disable** nếu ngày được chọn là ngày trong quá khứ.

---

## Luồng dữ liệu chính

### 1. Khởi tải
```
loadDates() → render dropdown ngày
    → loadData(date) → gọi API get_health_check_data
        → state.records / stats / groups / sections
        → renderActiveTab()
        → renderMiniBar()
```

### 2. Scan phát hồ sơ (distribute)
```
User nhập mã → setupScanForm('distribute') → live preview tên NV
    → Enter / nhấn nút → doScan('distribute')
        → kiểm tra: đã phát chưa? → hỏi xác nhận nếu có
        → gọi API scan_distribute(hospital_code/employee, date, note)
        → showScanResult()
        → addToHistory()
        → state.records được cập nhật qua realtime event
```

### 3. Scan thu hồ sơ (collect)
```
User nhập mã → doScan('collect')
    → kiểm tra: chưa phát? → hỏi nhập giờ phát thủ công
    → gọi API scan_collect(hospital_code/employee, date, x_ray, gynec, note, manual_start_time)
    → tương tự distribute
```

### 4. Realtime sync
```
Backend publish 'health_check_update' (Socket.IO)
    → setupRealtime() nhận event
    → cập nhật record trong state.records (tìm theo name)
    → recalculateStats()
    → partial update UI (không re-render toàn trang, tránh mất focus form)

Fallback: setupPollingAutoSync() → 3 giây/lần gọi get_health_check_data
    → so sánh hash để tránh update thừa
```

---

## Trạng thái record

```
pending (chưa khám)
    → distributed (đã phát HS) : start_time_actual != null
        → completed (hoàn thành) : end_time_actual != null
```

Hàm xác định: `getStatus(r)` → `'completed' | 'distributed' | 'pending'`

---

## Backend API — `health_check_api.py`

### API công khai (whitelist)

| Hàm | Method | Mô tả |
|---|---|---|
| `get_health_check_dates()` | GET | Danh sách ngày có dữ liệu (desc) |
| `get_health_check_data(date)` | GET | Toàn bộ records + stats + groups + sections |
| `scan_distribute(...)` | POST | Phát hồ sơ: ghi `start_time_actual = now()` |
| `scan_collect(...)` | POST | Thu hồ sơ: ghi `end_time_actual = now()` |
| `lookup_record(code, date)` | GET | Tìm record theo mã HS hoặc mã NV |
| `get_excel_data(date)` | GET | Xuất file Excel |

### `scan_distribute` — logic chi tiết
```python
1. _find_record(hospital_code, employee, date)
2. Ghi start_time_actual = nowtime()
3. Append note với prefix "[Cấp HS]" nếu có
4. doc.save(ignore_permissions=True)
5. _publish_update(date, doc, 'distribute')
6. Return { success, already_existed, record }
```
> Raise ValidationError nếu: không tìm thấy, hoặc đã có end_time_actual (đã thu rồi)

### `scan_collect` — logic chi tiết
```python
1. _find_record(hospital_code, employee, date)
2. Nếu manual_start_time và chưa có start_time_actual → ghi start_time_actual
3. Ghi end_time_actual = nowtime()
4. Cập nhật x_ray, gynecological_exam
5. Append note với prefix "[Thu HS]"
6. doc.save()
7. _publish_update(date, doc, 'collect')
```

### `_find_record` — tìm record
```python
# Ưu tiên: hospital_code → employee (full) → employee (4 số cuối LIKE)
if hospital_code:
    frappe.db.get_value("Health Check-Up", {"hospital_code": code, "date": date}, ...)
elif employee:
    if len(employee) == 4 and employee.isdigit():
        frappe.db.sql("... WHERE employee LIKE %s", f"%{employee}")
    else:
        frappe.db.get_value("Health Check-Up", {"employee": employee, "date": date}, ...)
```

### `_publish_update` — realtime
```python
frappe.publish_realtime(
    event="health_check_update",
    message={ date, action, ...record_fields },
    room="task_progress:health_check_updates",
    after_commit=True  # đảm bảo dữ liệu đã commit trước khi push
)
```

---

## Frontend — Các hàm quan trọng

### Dashboard

| Hàm | Mô tả |
|---|---|
| `renderDashboard()` | Render filter + stat cards + biểu đồ |
| `getDashboardFilteredRecords()` | Filter records theo start_time/section/group |
| `calcFilteredStats(records)` | Tính lại stats từ tập record đã filter |
| `updateDashboardStats()` | Cập nhật stats card mà không re-render toàn bộ |
| `showStatModal(type)` | Mở modal xem danh sách NV theo loại stat |
| `renderCharts()` | Vẽ biểu đồ Section + Group (Frappe Chart hoặc horizontal bar) |
| `renderMiniBar()` | Progress bar nhỏ ở header |

### Scan Form

| Hàm | Mô tả |
|---|---|
| `renderScanForm(mode)` | Render form scan (distribute/collect) |
| `setupScanForm(mode)` | Gắn event: live preview, auto-check gynec, Enter submit |
| `doScan(mode)` | Xử lý submit: validate → confirm nếu cần → gọi API |
| `showScanResult(type, msg, record)` | Hiển thị kết quả scan (success/update/error) |
| `populateScanHistory(mode)` | Lọc và sort lịch sử scan từ state.records |
| `renderHistory()` | Render bảng lịch sử scan |

### Danh sách NV

| Hàm | Mô tả |
|---|---|
| `renderEmployeeList()` | Render layout tab danh sách |
| `renderTable()` | Render bảng có sort, count, double-click mở doctype |
| `filterRecords()` | Lọc theo statusFilter + searchQuery |
| `setupListEvents()` | Gắn event search, filter button, sort header, double-click |

### Tiện ích

| Hàm | Mô tả |
|---|---|
| `getMinutesDifference(planned, actual)` | Tính chênh lệch phút (+ = trễ, - = sớm) |
| `isRecordLateForDistribute(r)` | So với ngưỡng `allowedLateDistribute` |
| `isRecordLateForCollect(r)` | So với ngưỡng `allowedLateCollect` |
| `formatTime(val)` | timedelta string → HH:MM hoặc "—" |
| `getProactiveNowTime()` | now nếu hôm nay, "23:59:59" nếu quá khứ |

---

## Fields của một Record

```
name                  (Frappe doc ID)
hospital_code         (mã hồ sơ, 4 ký tự)
employee              (mã NV)
employee_name
gender
department
custom_section
custom_group
designation
health_check_type
pregnant              (boolean)
start_time            (giờ hẹn phát)
end_time              (giờ hẹn thu)
start_time_actual     (thực tế phát - null nếu chưa phát)
end_time_actual       (thực tế thu - null nếu chưa thu)
x_ray                 (boolean)
gynecological_exam    (boolean)
note
```

---

## Debug nhanh

### Realtime không hoạt động?
→ Kiểm tra `setupPollingAutoSync()` có chạy không (fallback 3s)
→ Kiểm tra room name: `task_progress:health_check_updates`

### Scan báo không tìm thấy?
→ `_find_record()` tìm theo: hospital_code → employee đầy đủ → 4 số cuối
→ Kiểm tra đúng `date` không (mặc định = today)

### Tab Phát/Thu bị disable?
→ `loadData()` so sánh date với today, disable nếu quá khứ
→ Kiểm tra `state.currentDate`

### Stats không khớp?
→ `recalculateStats()` tính lại từ `state.records` (phía client)
→ `calcFilteredStats()` dùng cho dashboard (có thể khác stats tổng nếu đang filter)

### Export Excel lỗi?
→ `downloadExcel()` mở `/api/method/...get_excel_data?date=...`
→ Kiểm tra quyền và `build_xlsx_response()` trong Python

---

## File liên quan

```
health_check_up/
├── page/health_check_up_management/
│   ├── health_check_up_management.js   ← Frontend chính
│   ├── health_check_up_management.css  ← Style (light theme)
│   ├── health_check_up_management.html ← Template rỗng (chỉ có #root div)
│   ├── health_check_up_management.json ← Metadata page, roles
│   └── readme.md                       ← File này
├── api/
│   └── health_check_api.py             ← Backend API
└── doctype/health_check_up/            ← Doctype definition
```

Skill reference: `/home/frappe/frappe-bench/.agent/skills/health-check/`
