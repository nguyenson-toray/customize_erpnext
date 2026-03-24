# Health Check Up Management — Tài liệu kỹ thuật

## Tổng quan

Trang quản lý khám sức khỏe nhân viên. Gồm 2 file chính:
- **Frontend**: `health_check_up_management.js` (~1843 dòng)
- **Backend**: `../../api/health_check_api.py`

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
            └── setupPollingAutoSync()→ fallback polling (configurable, mặc định 3 giây)
```

---

## State (trạng thái toàn cục)

```javascript
state = {
    currentDate,           // ngày đang xem (YYYY-MM-DD)
    dates,                 // danh sách ngày có dữ liệu
    records,               // mảng toàn bộ record ngày hiện tại
    stats,                 // { total, distributed, completed, in_exam, not_started, x_ray, gynecological_exam, pregnant }
    groups,                // breakdown theo custom_group (tính bởi recalculateStats)
    sections,              // breakdown theo custom_section (tính bởi recalculateStats)
    activeTab,             // 'dashboard' | 'distribute' | 'collect' | 'list'
    searchQuery,           // chuỗi tìm kiếm tab danh sách
    statusFilter,          // filter trạng thái tab danh sách
    scanHistory,           // lịch sử scan (top 50)
    dashFilterStartTime,   // filter giờ hẹn trên dashboard
    dashFilterSection,     // filter section trên dashboard
    dashFilterGroup,       // filter group trên dashboard
    allowedLateDistribute, // ngưỡng trễ phát HS (phút)
    allowedLateCollect,    // ngưỡng trễ thu HS (phút)
    allowedEarlyDistribute,// ngưỡng sớm phát HS (phút)
    timeCompareMode,       // 'datetime' | 'time_only'
    chartLayout,           // 'vertical' | 'horizontal'
    pollingInterval,       // giây giữa các lần polling (mặc định 3, cấu hình qua dialog)
    sortField,             // cột đang sort
    sortOrder,             // 'asc' | 'desc'
}
```

> `state.groups` và `state.sections` được tính lại bởi `recalculateStats()` (không load từ server).

---

## 4 Tabs

| Tab | ID | Chức năng |
|---|---|---|
| Tổng quan | `dashboard` | Stat cards 3 nhóm + biểu đồ Section/Group |
| Phát Hồ Sơ | `distribute` | Scan phát hồ sơ, ghi `start_time_actual`. Badge hiển thị `đã phát / tổng` |
| Thu Hồ Sơ | `collect` | Scan thu hồ sơ, ghi `end_time_actual`. Badge hiển thị `đã thu / tổng` |
| Danh Sách NV | `list` | Bảng toàn bộ NV, search/filter/sort, export Excel |

> **Lưu ý**: Tab Phát/Thu bị **disable** nếu ngày được chọn là ngày trong quá khứ.

---

## Dashboard — Stat Cards

Chia thành 3 nhóm, mỗi nhóm có tiêu đề:

| Nhóm | Cards |
|---|---|
| Nhóm 1: Tiến độ chung | Tổng NV, Hoàn thành, Đang khám, Chưa khám |
| Nhóm 2: Thông tin thêm | Đã phát HS, Trễ phát, Trễ thu, Mang thai |
| Nhóm 3: Cận lâm sàng | X-Quang, Phụ khoa |

Click vào bất kỳ card nào → mở modal danh sách NV thuộc nhóm đó (có sort).

---

## Tab Thu HS — Chi tiết

- **Mini stats bar**: hiển thị tổng X-Quang và Phụ khoa đã thu trong ngày, cập nhật ngay sau mỗi scan thành công.
- **Auto-check checkbox**: khi scan ra mã NV, tự động tick X-Quang (trừ NV mang thai) và Phụ khoa (chỉ NV nữ).
- **Button text**: hiện tên NV + group khi scan. Nếu NV nữ mang thai → thêm emoji `🤰`.
- **Reset form**: chỉ xoá input sau khi API thành công; nếu lỗi, input giữ nguyên để scan lại.

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
User nhập mã → setupScanForm('distribute') → live preview tên NV
    → Enter / nhấn nút → doScan('distribute')
        → kiểm tra: đã phát chưa? → hỏi xác nhận nếu có
        → gọi API scan_distribute(hospital_code/employee, date, note)
        → showScanResult() + addToHistory()
        → cập nhật state.records[idx] trực tiếp
        → recalculateStats() + updateTabCounts()
```

### 3. Scan thu hồ sơ (collect)
```
User nhập mã → doScan('collect')
    → kiểm tra: chưa phát? → hỏi nhập giờ phát thủ công
    → gọi API scan_collect(hospital_code/employee, date, x_ray, gynec, note, manual_start_time)
    → cập nhật state.records[idx] trực tiếp
    → recalculateStats() + updateTabCounts() + renderCollectMiniStats()
```

### 4. Realtime sync
```
Backend publish 'health_check_update' (Socket.IO)
    → setupRealtime() nhận event
    → cập nhật record trong state.records (tìm theo name)
    → recalculateStats() + updateTabCounts()
    → partial update UI theo activeTab (không re-render toàn trang)

Fallback: setupPollingAutoSync() → state.pollingInterval giây/lần
    → so sánh hash để tránh update thừa
    → nếu có thay đổi: recalculateStats() + updateTabCounts() + partial update
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
| `get_health_check_data(date)` | GET | Toàn bộ records + stats |
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
| `renderDashboard()` | Render stat cards 3 nhóm (có tiêu đề) + biểu đồ |
| `getDashboardFilteredRecords()` | Filter records theo start_time/section/group |
| `calcFilteredStats(records)` | Tính stats từ tập record đã filter (bao gồm late_dist/late_coll) |
| `updateDashboardStats()` | Cập nhật stat cards mà không re-render toàn bộ (dùng cho realtime) |
| `showStatModal(type)` | Mở modal xem danh sách NV theo loại stat (có sort) |
| `renderCharts()` | Vẽ biểu đồ Section + Group (Frappe Chart hoặc horizontal bar) |

### Scan Form

| Hàm | Mô tả |
|---|---|
| `renderScanForm(mode)` | Render form scan (distribute/collect) |
| `renderCollectMiniStats()` | Render HTML badge X-Quang/Phụ khoa từ state.stats (dùng chung 3 chỗ) |
| `setupScanForm(mode)` | Gắn event: live preview, auto-check gynec, pregnant emoji, Enter submit |
| `doScan(mode)` | Xử lý submit: validate → confirm nếu cần → gọi API → cập nhật state trực tiếp |
| `showScanResult(type, msg, record)` | Hiển thị kết quả scan (success/update/error) |
| `populateScanHistory(mode)` | Lọc và sort lịch sử scan từ state.records |
| `renderHistory()` | Render bảng lịch sử scan |

### Tab Badge / Counts

| Hàm | Mô tả |
|---|---|
| `updateTabCounts()` | Cập nhật badge `đã phát/tổng` và `đã thu/tổng` trên tab buttons |

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
| `recalculateStats()` | Tính lại state.stats + state.groups + state.sections từ state.records |
| `getMinutesDifference(planned, actual)` | Tính chênh lệch phút theo time only |
| `getMinutesDiffDatetime(...)` | Tính chênh lệch phút theo full datetime |
| `getMinutesDiffByMode(...)` | Wrapper chọn mode tính dựa theo state.timeCompareMode |
| `isRecordLateForDistribute(r)` | So với ngưỡng `allowedLateDistribute` |
| `isRecordLateForCollect(r)` | So với ngưỡng `allowedLateCollect` |
| `getProactiveNow()` | Trả `{date, time}` của "now" theo mode và currentDate |
| `formatTime(val)` | timedelta string → HH:MM hoặc "—" |

---

## Cấu hình (dialog "Cấu hình" trên Dashboard)

| Tùy chọn | State key | Mặc định | Mô tả |
|---|---|---|---|
| Phút khám trễ cho phép | `allowedLateDistribute` | 10 | Ngưỡng highlight "Trễ phát" |
| Phút nộp HS trễ cho phép | `allowedLateCollect` | 0 | Ngưỡng highlight "Trễ thu" |
| Phút khám sớm cho phép | `allowedEarlyDistribute` | 10 | Ngưỡng highlight "Sớm phát" |
| Cách so sánh thời gian | `timeCompareMode` | datetime | `datetime` hoặc `time_only` |
| Hướng biểu đồ | `chartLayout` | vertical | `vertical` hoặc `horizontal` |
| Polling interval (giây) | `pollingInterval` | 3 | Tần suất auto-sync fallback; restart polling khi thay đổi |

---

## Fields của một Record

```
name                  (Frappe doc ID)
hospital_code         (mã hồ sơ)
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
start_time_actual     (thực tế phát — null nếu chưa phát)
end_time_actual       (thực tế thu — null nếu chưa thu)
x_ray                 (boolean)
gynecological_exam    (boolean)
note
```

---

## Debug nhanh

### Realtime không hoạt động?
→ Kiểm tra `setupPollingAutoSync()` có chạy không (fallback mặc định 3s)
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
→ Dashboard filter không ảnh hưởng `state.stats`, chỉ ảnh hưởng hiển thị cards

### Mini stats X-Quang/Phụ khoa không cập nhật?
→ Sau scan: cập nhật ngay qua `renderCollectMiniStats()`
→ Qua realtime: cập nhật trong handler `case "collect"`
→ Qua polling: cập nhật sau khi phát hiện hash thay đổi

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
│   ├── health_check_up_management.html ← Template rỗng
│   ├── health_check_up_management.json ← Metadata page, roles
│   └── readme.md                       ← File này
├── api/
│   └── health_check_api.py             ← Backend API
└── doctype/health_check_up/            ← Doctype definition
```

Skill reference: `/home/frappe/frappe-bench/.agent/skills/health-check/`
