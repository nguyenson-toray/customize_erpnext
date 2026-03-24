# Biometric Sync — `/biometric_sync`

Trang quản lý đồng bộ dữ liệu chấm công vân tay giữa các máy chấm công (ZKTeco / compatible) và ERPNext.

---

## Kiến trúc tổng quan

```
Browser (index.html)
    │
    ├── callGet(method, args)   → GET  /api/method/<method>?...    (read-only, không cần CSRF)
    └── callPost(method, args)  → POST /api/method/<method>        (write, kèm csrf_token trong FormData)

Server (Frappe whitelisted methods)
    ├── customize_erpnext.api.biometric_sync.*
    ├── customize_erpnext.api.utilities.*
    └── customize_erpnext.api.biometric_log_viewer.*
```

**CSRF**: Token được inject từ Python context qua Jinja (`window.csrf_token = "{{ csrf_token }}"`).
Frappe validate CSRF từ **form body** — không dùng header. Tất cả POST dùng `FormData` với `csrf_token` appended.

**Authentication**: `index.py` kiểm tra `frappe.session.user == "Guest"`, nếu đúng redirect về `/login?redirect-to=/biometric_sync`.

---

## Cấu trúc file

```
www/biometric_sync/
├── index.html   — Toàn bộ UI + JS logic (single-page, no framework)
├── index.py     — Frappe context: kiểm tra login, inject csrf_token
└── readme.md    — Tài liệu này
```

---

## 5 Tab chức năng

### Tab 1 — Log Viewer

**Mục đích**: Xem file log của hệ thống biometric sync trực tiếp trên trình duyệt.

**Luồng**:
1. `loadLogFiles()` — gọi `GET biometric_log_viewer.get_log_files` → populate dropdown.
   Nếu có file `logs.log` thì tự động load ngay.
2. `loadLog()` — gọi `GET biometric_log_viewer.get_log_content?log_file=<tên>` → nhận nội dung text.
   Tách thành mảng `allLines[]`, **đảo ngược thứ tự** (dòng mới nhất hiển thị trên cùng).
3. `filterLines()` — lọc client-side theo:
   - **Level**: ALL / ERROR / WARNING / INFO (kế thừa: WARNING hiển thị cả ERROR, INFO hiển thị tất cả)
   - **Search text**: `toLowerCase()` match
   - Tô màu dòng theo level: đỏ (ERROR/CRITICAL), vàng (WARNING), xanh dương (INFO)

---

### Tab 2 — Sync Device → Device & ERP

**Mục đích**: Đọc dữ liệu vân tay từ **máy nguồn (master)** và đẩy sang ERPNext và/hoặc các máy đích.

#### Khởi tạo
- `loadMachinesForFingerprint()` gọi `GET utilities.get_enabled_attendance_machines` → `_allMachines[]`
- Render dropdown chọn máy nguồn + danh sách checkbox máy đích

#### Chọn máy nguồn & đích
- **Máy nguồn**: dropdown `#masterMachine` — chọn 1 máy làm master.
- **Máy đích**: checkbox list `#targetMachineList` — tất cả máy **trừ master**, mặc định **checked all**.
- Nút **All** / **None** gọi `selectAllTargets(checked)`.
- **Sync to ERPNext**: checkbox `#fpSyncToErp`, mặc định bật.

#### Load users từ master
`loadMasterUsers()` → `GET biometric_sync.get_master_device_users?machine_name=<master>`
Kết quả lưu vào `_masterUsers[]` — mỗi user có: `user_id`, `employee_id`, `employee_name`, `device_name`, `date_of_joining`, `matched` (bool — có trong ERPNext hay không).

#### Lọc nhân viên từ ERPNext (tùy chọn)
`applyEmployeeFilter()` → `GET biometric_sync.get_employees_for_sync` với các tham số:
- `employee` (Employee ID), `employee_name`, `attendance_device_id`, `date_of_joining`

Kết quả: tập hợp `_filteredDeviceIds` (Set of string). Khi render bảng, chỉ hiển thị user có `user_id` nằm trong set này.

#### Render bảng user
`renderUserTable(users)`:
- Áp filter `_filteredDeviceIds` nếu có
- Row **matched** (có trong ERPNext): checkbox checked, cho phép chọn
- Row **unmatched**: checkbox disabled, không thể chọn
- Hiển thị badge Matched / Unmatched

#### Trạng thái nút Sync
`updateSyncButton()` tính:
```
hasDestination = (checkedTargets > 0) OR (fpSyncToErp === true)
btn.disabled   = (selectedUsers === 0) OR NOT hasDestination
```
Summary: `"▶ Sync N users → ERPNext + M machines"`

#### Thuật toán Sync (`startSync()`)

```
1. Thu thập selectedUserIds (user_id từ máy)
2. Thu thập targetMachines (máy đích checked)
3. Tính matchedUsers = _masterUsers filter (user_id in selected AND matched AND employee_id exists)
4. employeeIds = matchedUsers.map(employee_id)

─── Nếu syncToErp = true ───────────────────────────────────────────────
5. POST check_employees_fingerprints_in_erp(employee_ids_json)
   → existing = {employee_id: count, ...}
   → Nếu có existing: confirm overwrite (hiển thị tối đa 5 tên)

6. Confirm tổng (source, destinations)

─── Phase 1: Device → ERPNext ──────────────────────────────────────────
7. POST sync_fingerprints(master, targets=[], user_ids, sync_to_erp=1)
   → trả về { job_id }
8. pollSyncJob(job_id, machines=[], totalUsers, erpDestId='__erp__')
   → polling mỗi 1500ms qua GET get_sync_job_status?job_id=<id>
   → cập nhật progress bar '__erp__'
   → append result lines vào log
   → resolve() khi status='done', reject() khi status='error'

─── Phase 2: ERPNext → Devices (nếu có targetMachines) ─────────────────
9. runPhase2(employeeIds, matchedUsers, targetMachines)
   for machine in targetMachines:
     for empId in employeeIds:
       POST utilities.sync_employee_to_single_machine(employee_id, machine_name)
       → cập nhật progress bar từng máy
   (tuần tự theo máy, tuần tự theo nhân viên)

─── Nếu syncToErp = false ──────────────────────────────────────────────
→ POST sync_fingerprints(master, targets=targetMachines, user_ids, sync_to_erp=0)
→ pollSyncJob(job_id, machines=targetMachines, totalUsers, erpDestId=null)
```

#### Polling job (`pollSyncJob`)
- Interval 1500ms, gọi `GET get_sync_job_status?job_id=<id>`
- Cập nhật progress bar theo `progress_pct`, `done_users`
- Append kết quả từng user (chỉ append dòng mới: `slice(lastCount)`)
- `status='done'` → `resolve()`, `status='error'` → `reject()`
- Trả về `Promise` — cho phép `await` trong `startSync()`

---

### Tab 3 — Sync ERP → Machines

**Mục đích**: Đẩy dữ liệu nhân viên từ ERPNext xuống máy chấm công (không cần đọc từ thiết bị trước).

#### Chọn nhân viên (3 chế độ)
| Scope | Logic |
|-------|-------|
| `all` | `GET get_employees_for_sync` không tham số → tất cả nhân viên active |
| `date` | `GET get_employees_for_sync?date_of_joining=<date>` → nhân viên vào từ ngày ≥ |
| `manual` | Nhập tay danh sách Employee ID (mỗi dòng 1 ID) — không gọi API, build array trực tiếp |

Kết quả lưu vào `_fp41Employees[]`.

#### Chọn máy đích
- Render từ `_allMachines[]` (đã load ở Tab 2)
- Online machines: checked mặc định; offline: unchecked
- Nút **All** / **None**

#### Trạng thái nút Sync
```
btn.disabled = (_fp41Employees.length === 0) OR (selMachines === 0) OR (_fp41Syncing)
summary = "▶ Will sync N employees → M machines (N×M operations)"
```

#### Thuật toán Sync (`fp41StartSync()`)
```
confirm(N employees × M machines = total operations)

for machine in selMachines:
  for emp in _fp41Employees:
    POST utilities.sync_employee_to_single_machine(employee_id, machine_name)
    → ok/fail → append log
    done++
    barEl.width = done/total * 100%
```
**Tuần tự hoàn toàn** (machine × employee) — tránh quá tải thiết bị.

---

### Tab 4 — Remove Left Staff

**Mục đích**: Xóa nhân viên đã nghỉ việc khỏi máy chấm công (giữ nguyên dữ liệu trong ERPNext).

**Nguyên tắc an toàn**:
- Nhân viên **active** → **KHÔNG BAO GIỜ** bị xóa
- Dữ liệu vân tay trong **ERPNext KHÔNG bị xóa** — chỉ xóa trên thiết bị
- Chỉ xóa nhân viên **resigned** đã qua `delay_days` sau `relieving_date`

#### Cấu hình
- `delay_days`: 15 / 30 / 45 (default) / 60 / 90 ngày sau `relieving_date`
- `include_unmatched`: tùy chọn xóa cả user_id trên thiết bị không khớp với nhân viên nào trong ERPNext

#### Luồng 2 bước

**Bước 1 — Scan** (`del43Scan()`):
```
POST biometric_sync.get_left_employees_on_machines(delay_days, include_unmatched)
→ {
    users_to_delete: [{user_id, employee_id, employee_name, reason, reason_type,
                       relieving_date, days_since_relieving, machines[]}],
    machines_scanned: [{machine, success, total_users, error}],
    total_unique_user_ids, users_to_keep_count, today, delay_days
  }
```
Render bảng preview với checkbox per-user (mặc định checked all).
Phân loại: `reason_type='left_employee'` (nghỉ việc) vs `'unmatched'` (không có trong ERPNext).

**Bước 2 — Delete** (`del43Delete()`):
```
1. Thu thập selected users từ checkbox
2. confirm("N users — cannot be undone")
3. POST biometric_sync.delete_users_from_machines(users_json)
   → {job_id}
4. Polling GET get_sync_job_status?job_id=<id> mỗi 1500ms
   → cập nhật progress bar
   → append log kết quả từng user × machine
   → done/error → dừng timer
```

---

### Tab 5 — Machine Management

**Mục đích**: Xem thông tin và quản lý từng máy chấm công.

**Lazy load**: Chỉ load khi người dùng click vào tab lần đầu (`_machinesLoaded` flag).

#### Danh sách máy
`GET biometric_sync.get_attendance_machines` → render machine cards.
Mỗi card hiển thị: tên, device name, IP:port, location, badge "★ Master" nếu là master.

#### Actions từng máy

| Action | API | Logic |
|--------|-----|-------|
| **Info** | `POST machine_get_info` | Đọc firmware, serial, platform, FP version, user/FP/record count + capacity, device time, MAC address. Hiển thị capacity bar (xanh <60%, vàng 60-85%, đỏ >85%). |
| **Sync Time** | `POST machine_sync_time` | Đồng bộ thời gian máy chấm công với server time. Hiển thị server time vs device time. |
| **Reboot** | `POST machine_reboot` | Gửi lệnh restart thiết bị. Yêu cầu confirm trước. |

#### Bulk actions

| Action | Logic |
|--------|-------|
| **Refresh** | Reset flag + reload toàn bộ danh sách |
| **Sync Time All** | `Promise.allSettled()` — **song song** tất cả máy |
| **Reboot All** | **Tuần tự** với delay 800ms/máy — tránh gây sốc điện |
| **Load Info All** | `Promise.allSettled()` — song song, cập nhật từng row khi có kết quả. Pre-fill spinner cho tất cả rows trước khi gọi. |

---

## API endpoints sử dụng

### GET (read-only)

| Method | Mô tả |
|--------|-------|
| `biometric_log_viewer.get_log_files` | Danh sách file log |
| `biometric_log_viewer.get_log_content?log_file=` | Nội dung file log |
| `utilities.get_enabled_attendance_machines` | Danh sách máy đang bật |
| `biometric_sync.get_master_device_users?machine_name=` | Users trên máy chấm công + match với ERPNext |
| `biometric_sync.get_employees_for_sync` | Nhân viên active từ ERPNext, filter tùy chọn |
| `biometric_sync.get_sync_job_status?job_id=` | Trạng thái background job |
| `biometric_sync.get_attendance_machines` | Tất cả máy (kể cả disabled) |

### POST (write, cần CSRF)

| Method | Mô tả |
|--------|-------|
| `biometric_sync.check_employees_fingerprints_in_erp` | Kiểm tra nhân viên đã có vân tay trong ERP chưa |
| `biometric_sync.sync_fingerprints` | Tạo background job đồng bộ vân tay từ thiết bị |
| `utilities.sync_employee_to_single_machine` | Đẩy 1 nhân viên xuống 1 máy |
| `biometric_sync.get_left_employees_on_machines` | Scan nhân viên cần xóa khỏi máy |
| `biometric_sync.delete_users_from_machines` | Tạo background job xóa users khỏi máy |
| `biometric_sync.machine_get_info` | Đọc hardware info từ thiết bị |
| `biometric_sync.machine_sync_time` | Đồng bộ thời gian thiết bị |
| `biometric_sync.machine_reboot` | Reboot thiết bị |

---

## State variables (JS globals)

| Biến | Dùng trong | Mô tả |
|------|-----------|-------|
| `_allMachines[]` | Tab 2, 3 | Danh sách tất cả máy enabled |
| `_masterUsers[]` | Tab 2 | Users đọc được từ máy nguồn, kèm match info |
| `_filteredDeviceIds` | Tab 2 | Set device IDs từ filter ERPNext, hoặc `null` |
| `_pollTimer` | Tab 2 | setInterval handle cho job polling |
| `_fp41Employees[]` | Tab 3 | Danh sách nhân viên chọn để sync |
| `_fp41Syncing` | Tab 3 | Flag đang sync (disable nút) |
| `_del43ScanResult` | Tab 4 | Kết quả scan lần cuối |
| `_del43PollTimer` | Tab 4 | setInterval handle cho delete job polling |
| `_machinesList[]` | Tab 5 | Danh sách máy cho machine management |
| `_machinesLoaded` | Tab 5 | Lazy load flag |

---

## Xử lý lỗi

**`callGet` / `callPost`**:
- HTTP 401/403 → `location.reload()` (session expired)
- Response không phải JSON → throw "not JSON"
- `data.exc` hoặc `data.exc_type` → parse `_server_messages` → throw message
- `data.message === undefined` → throw "empty response"

**Pattern parse Frappe error**:
```javascript
function _parseFrappeError(data, httpStatus) {
    // frappe.throw() → exc + _server_messages (không có message key)
    let msg = '';
    try { msg = JSON.parse(JSON.parse(data._server_messages || '[]')[0]).message; } catch {}
    return msg || data.exc_type || data.exc || `HTTP ${httpStatus}`;
}
```

---

## Desktop Icon & Workspace Sidebar

- **Desktop Icon**: `fixtures/desktop_icon.json` — name="Biometric Sync", link="/biometric_sync", icon_type="Link", link_type="External"
- **Workspace Sidebar**: Bắt buộc phải có record `tabWorkspace Sidebar` tên "Biometric Sync" với ít nhất 1 item type khác Section Break — nếu thiếu, Frappe `is_permitted()` trả về `False` và icon không hiển thị trên desktop.
