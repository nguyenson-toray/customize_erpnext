# Attendance Request — Bổ sung giờ check in/out (Plan)

> **Mục đích:** Kế hoạch dùng doctype Attendance Request làm phiếu yêu cầu bổ sung giờ chấm công khi nhân viên quên quét vân tay, máy lỗi hoặc ngày làm đầu tiên.
> **Phạm vi:** Tài liệu
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-20

> Trạng thái: **PLAN — chưa code**. Ngày lập: 2026-08-15.
> Mục tiêu: dùng doctype `Attendance Request` (HRMS) làm phiếu **yêu cầu bổ sung giờ chấm công**
> cho trường hợp nhân viên quên quét vân tay, máy lỗi, ngày làm việc đầu tiên…

---

## 1. Quyết định thiết kế (user đã chốt)

| Vấn đề | Quyết định |
|---|---|
| Cấu trúc nhập giờ | **Child table theo ngày**: giữ `from_date`/`to_date`, tự sinh 1 dòng/ngày với cột `Date · Existing In · Existing Out · New In · New Out` |
| Phân biệt chế độ | **Suy ra từ `reason`** — không thêm field Request Type |
| Cập nhật Attendance | **Chạy lại engine** `_core_process_attendance_logic_optimized` (không viết công thức OT mới) |
| Khi Cancel | **Xoá Employee Checkin đã tạo + tính lại công** |

### Chế độ (mode)

```python
SUPPLEMENT_REASONS = {"Forget Check In/Out", "Machine Error", "First Working Day", "Other"}
```

- `reason ∈ SUPPLEMENT_REASONS` → **chế độ bổ sung checkin** (logic mới).
- `reason ∈ {"Work From Home", "On Duty"}` → **giữ nguyên 100% hành vi HRMS gốc** (`super()`).

4 giá trị mới **trùng khít** danh sách của `Employee Checkin.custom_reason_for_manual_check_in`
(`First Working Day / Forget Check In/Out / Machine Error / Other`) ⇒ khi tạo checkin chỉ cần
copy thẳng, không cần bảng ánh xạ.

---

## 2. Data model

### 2.1 Child DocType mới — `Attendance Request Checkin Detail`

Vị trí: `customize_erpnext/customize_erpnext/doctype/attendance_request_checkin_detail/`
(`istable = 1`, module `Customize Erpnext`).
⚠ **Bắt buộc có `__init__.py` + file controller `.py`** — thiếu sẽ `ImportError: Module import failed`
khi insert parent.

| fieldname | type | label | ghi chú |
|---|---|---|---|
| `date` | Date | Date | reqd, read_only, in_list_view — tự sinh từ khoảng ngày |
| `day_of_week` | Data | Day | read_only, in_list_view — Mon/Tue/… để nhận ra Chủ Nhật |
| `existing_status` | Data | Att. Status | read_only — `Present` / `Absent` / `Holiday` / `-` |
| `existing_in_time` | Data | Existing In | read_only, in_list_view — format `HH:mm` |
| `existing_out_time` | Data | Existing Out | read_only, in_list_view — format `HH:mm` |
| `existing_working_hours` | Float | Hours | read_only |
| `new_in_time` | Time | New In | optional, in_list_view |
| `new_out_time` | Time | New Out | optional, in_list_view |
| `remark` | Small Text | Remark | optional, ghi chú theo dòng |
| `created_checkin_in` | Link → Employee Checkin | Created Check In | read_only, **`no_copy: 1`** |
| `created_checkin_out` | Link → Employee Checkin | Created Check Out | read_only, **`no_copy: 1`** |

`no_copy` trên 2 field `created_*` là bắt buộc: khi **Amend** một phiếu đã cancel, child rows được
copy sang phiếu mới — nếu không `no_copy` thì phiếu mới trỏ vào checkin đã bị xoá.

Các cột `existing_*` chỉ để **hiển thị** (đúng yêu cầu "khi save show thêm giờ check in đã có"),
không tham gia tính toán.

### 2.2 Custom Field trên `Attendance Request`

| fieldname | type | ghi chú |
|---|---|---|
| `custom_supplement_section` | Section Break | label `Check In / Out Supplement`, insert_after `shift`, `depends_on` = eval theo reason |
| `custom_checkin_details` | Table | options `Attendance Request Checkin Detail`, cùng `depends_on` |

### 2.3 Custom Field trên `Employee Checkin`

| fieldname | type | ghi chú |
|---|---|---|
| `custom_attendance_request` | Link → Attendance Request | read_only, insert_after `custom_other_reason_for_manual_check_in` |

Dùng để (a) truy vết checkin sinh từ phiếu nào, (b) tìm & xoá khi Cancel.

### 2.4 Property Setter — `Attendance Request.reason.options`

```
Work From Home
On Duty
Forget Check In/Out
Machine Error
First Working Day
Other
```

### 2.5 Fixtures (`hooks.py`)

- Thêm `"Attendance Request"` vào filter list của **Custom Field** (đã có điều kiện `fieldname like custom%`).
- Thêm `"Attendance Request"` vào filter list của **Property Setter**.
- `Employee Checkin` đã có sẵn trong cả hai list → field mới tự được export.

---

## 3. Server — `overrides/attendance_request/attendance_request.py`

`override_doctype_class["Attendance Request"] = "...CustomAttendanceRequest"`
(tiền lệ: `CustomLeaveApplication`, `CustomSalarySlip`).

```python
class CustomAttendanceRequest(AttendanceRequest):
    @property
    def is_supplement(self) -> bool:
        return self.reason in SUPPLEMENT_REASONS
```

### 3.1 `validate()`

```python
def validate(self):
    if not self.is_supplement:
        return super().validate()          # WFH / On Duty: y hệt HRMS

    validate_active_employee(self.employee)
    validate_dates(self, self.from_date, self.to_date, False)
    self.validate_shifts()                 # tái dùng của HRMS
    self.sync_checkin_rows()
    self.refresh_existing_times()
    self.validate_supplement_rows()
    self.validate_supplement_overlap()
```

**Cố ý KHÔNG gọi 3 validate của HRMS trong chế độ bổ sung:**

| Bỏ qua | Lý do |
|---|---|
| `validate_no_attendance_to_create()` | Ngày cần bổ sung hầu như luôn đã có Attendance ⇒ nó throw *"Attendance status unchanged"* và **chặn mọi phiếu bổ sung** |
| `validate_request_overlap()` | Chặn theo cả khoảng ngày ⇒ không thể tạo 1 phiếu bù IN và 1 phiếu bù OUT cùng ngày. Thay bằng kiểm tra trùng theo **dòng + chiều in/out** (§3.5) |
| `validate_half_day()` | `half_day` không liên quan; JS sẽ ẩn field này |

### 3.2 `sync_checkin_rows()`

- Sinh danh sách ngày `from_date → to_date`.
- Giữ nguyên dòng cũ còn trong khoảng (không mất giờ user đã nhập), bỏ dòng ngoài khoảng,
  thêm dòng thiếu, sort theo `date`.
- Set `day_of_week`.
- **Không** bỏ Chủ Nhật / ngày lễ (có thể cần bù công OT ngày CN) — chỉ đánh dấu vào `existing_status`.

### 3.3 `refresh_existing_times()`

Với mỗi dòng, đọc `Attendance` (`docstatus != 2`) của `(employee, date)`:
`status`, `in_time`, `out_time`, `working_hours` → đổ vào các cột `existing_*` (format `HH:mm`).
Không có Attendance → `existing_status = "-"`. Chạy mỗi lần save ⇒ số liệu luôn tươi.

### 3.4 `validate_supplement_rows()`

1. Toàn phiếu phải có ≥ 1 dòng nhập `new_in_time` hoặc `new_out_time`, nếu không → throw.
2. Cùng dòng có cả 2 → `new_in_time < new_out_time`.
3. Có `new_in_time` và đã tồn tại `out_time` → `new_in_time` phải **trước** `out_time`.
4. Có `new_out_time` và đã tồn tại `in_time` → `new_out_time` phải **sau** `in_time`.
5. Giờ nhập không được trùng Employee Checkin đã có trong ngày (sai lệch ≤ 1 phút) → throw.
6. Ngày đã có đủ cả in & out mà vẫn bù cùng chiều → `msgprint` cảnh báo (không chặn — có thể là sửa đúng).
7. `reason == "Other"` → bắt buộc nhập `explanation`.

### 3.5 `validate_supplement_overlap()`

Query child table join parent: có phiếu **đã submit** khác nào đã bù đúng `(employee, date, chiều in/out)` chưa.
Trùng → throw kèm link phiếu cũ. Phiếu draft bỏ qua.

### 3.6 `get_attendance_warnings()` — override trả `[]` khi supplement

HRMS JS gọi method này ở `refresh` và vẽ banner *"Attendance status unchanged"* cho mọi ngày —
vô nghĩa và gây hoang mang trong chế độ bù công. Override trả list rỗng ⇒ banner tự tắt,
không phải hack ở JS.

### 3.7 `on_submit()`

```python
def on_submit(self):
    if not self.is_supplement:
        return super().on_submit()
    self.create_supplement_checkins()
    self.recalculate_attendance()
```

**`create_supplement_checkins()`** — mỗi giờ nhập → 1 `Employee Checkin`:

| field | giá trị |
|---|---|
| `employee` | `self.employee` |
| `time` | `datetime.combine(row.date, row.new_in_time)` |
| `log_type` | `IN` / `OUT` (hook `update_employee_checkin` sẽ tự chuẩn hoá lại theo thứ tự trong ngày) |
| `shift` | `self.shift` |
| `skip_auto_attendance` | `0` |
| `custom_reason_for_manual_check_in` | `self.reason` (trùng khít option của Employee Checkin) |
| `custom_other_reason_for_manual_check_in` | `self.explanation` khi reason = `Other` |
| `custom_attendance_request` | `self.name` |

Lưu tên checkin vừa tạo vào `row.created_checkin_in` / `created_checkin_out` (`db_set`).

**`recalculate_attendance()`**:

```python
_core_process_attendance_logic_optimized(
    employees=[self.employee],
    days=[getdate(r.date) for r in rows_with_new_time],
    from_date=self.from_date, to_date=self.to_date,
    fore_get_logs=True,
)
```

- Gọi **thẳng** hàm core, **không** qua `_recalculate_attendance_background` — wrapper đó có cổng
  `is_peak_time()` và cổng setting `recalc_attendance_on_checkin_change` (mặc định OFF);
  user bấm Submit thì phải chạy ngay, không được im lặng bỏ qua.
- Chạy đồng bộ (1 nhân viên × vài ngày). ⚠ **Phải đo thời gian thật ở bước test.** Nếu > ~10s
  thì chuyển sang `frappe.enqueue` + `publish_realtime` theo khuôn mẫu
  `bulk_update_attendance_optimized` (gunicorn timeout 120s).
- Bọc `try/except` → `frappe.log_error` + `msgprint` cảnh báo *"Check-ins created but attendance
  recalculation failed — run Bulk Update Attendance for this date"*. **Không nuốt lỗi im lặng.**

### 3.8 `on_cancel()`

```python
def on_cancel(self):
    if not self.is_supplement:
        return super().on_cancel()     # HRMS: cancel các Attendance đã tạo
    self.delete_supplement_checkins()
    self.recalculate_attendance()
```

- Xoá các `Employee Checkin` có `custom_attendance_request = self.name` (bỏ qua bản ghi đã bị
  xoá tay). Clear `created_checkin_*` trên các dòng.
- Sau khi xoá, gọi lại `update_remaining_checkins_after_delete()` (đã có sẵn trong
  `overrides/employee_checkin/employee_checkin.py`) để chuẩn hoá `log_type` của các checkin còn lại
  — hàm này hiện **không** được đăng ký ở `doc_events`, phải gọi tường minh.
- Rồi chạy lại engine ⇒ Attendance quay về đúng trạng thái trước khi bù (kể cả về lại `Absent`).

---

## 4. Client — `public/js/custom_scripts/attendance_request.js`

- `reason` / `refresh`: chế độ bù → ẩn `half_day`, `half_day_date`, `include_holidays`;
  hiện section child table. Ngược lại thì ẩn section.
- `from_date` / `to_date` đổi → sinh trước các dòng ngày ngay trên client cho user nhập luôn
  (server vẫn `sync_checkin_rows()` lại khi save — client chỉ là tiện dụng).
  ⚠ **Tuyệt đối không dùng `Date.toISOString()`** (lệch 1 ngày) — dùng `frappe.datetime.add_days` /
  `frappe.datetime.get_today`.
- Sau khi save (doc không còn `is_new`): vẽ `frm.dashboard.add_section` bảng **Existing Check-ins**
  liệt kê *toàn bộ* Employee Checkin thô của từng ngày (không chỉ in/out của Attendance) —
  lấy qua 1 whitelisted method. Đây là phần "show thêm giờ check in đã tồn tại".
- Nút **"Refresh Existing Times"** trên toolbar (chỉ khi draft): gọi lại server, cập nhật các cột
  `existing_*` + dashboard mà không cần save.
- Mọi string UI viết **tiếng Anh trong `__()`**, dịch bổ sung vào `translations/vi.csv`.
- `frappe.call` dùng `freeze: true` + `freeze_message` cụ thể (không để "Loading...").

---

## 5. hooks.py

```python
doctype_js["Attendance Request"] = "public/js/custom_scripts/attendance_request.js"

override_doctype_class["Attendance Request"] = \
    "customize_erpnext.overrides.attendance_request.attendance_request.CustomAttendanceRequest"

# fixtures: thêm "Attendance Request" vào cả Custom Field và Property Setter
```

⚠ **Sửa `hooks.py` → bắt buộc `bench restart`** (bench console cho false positive khi verify hooks).
Production đang giờ làm việc ⇒ **hỏi user trước khi restart**.

---

## 6. Thứ tự triển khai

| # | Bước | Ghi chú |
|---|---|---|
| 0 | Kiểm tra `bench migrate` có chạy được không | ⚠ Memory: migrate đang **gãy sẵn** vì app `DuckDB Sync` thiếu `pyarrow`. Nếu vẫn gãy → import doctype JSON trực tiếp bằng `import_file_by_path` trong console thay vì migrate |
| 1 | Tạo child DocType `Attendance Request Checkin Detail` (JSON + `__init__.py` + controller) | |
| 2 | Tạo Custom Field (2 trên AR, 1 trên Employee Checkin) + Property Setter cho `reason.options` | qua console hoặc patch |
| 3 | Viết `overrides/attendance_request/attendance_request.py` + `attendance_request.md` | |
| 4 | Viết `public/js/custom_scripts/attendance_request.js` | |
| 5 | Cập nhật `hooks.py` (doctype_js, override_doctype_class, fixtures) | |
| 6 | Bổ sung `translations/vi.csv` | string có dấu phẩy phải quote |
| 7 | `bench build --app customize_erpnext` + `bench clear-cache` | |
| 8 | **Hỏi user** rồi `bench restart` | |
| 9 | `bench export-fixtures` sau khi user test OK | |

⚠ **Nếu UI không khớp source JS → assets chưa build lại** (kiểm tra bundle trong `sites/assets`,
đừng tin thư mục `apps/`).

---

## 7. Checklist test (user test trên UI thật trước khi commit)

| # | Kịch bản | Kỳ vọng |
|---|---|---|
| A | 1 ngày, đã có IN thiếu OUT → nhập New Out | Tạo 1 EC; Attendance có `out_time`, `working_hours` đúng, OT đúng nếu có Overtime Registration |
| B | 1 ngày, đã có OUT thiếu IN → nhập New In | Tương tự, `in_time` đúng, `late_entry` tính lại |
| C | 1 ngày `Absent` (không có checkin) → nhập cả 2 | Tạo 2 EC; Attendance `Absent → Present` |
| D | 3 ngày, chỉ 2 ngày nhập giờ | Chỉ tạo checkin cho 2 ngày có giờ |
| E | Cancel phiếu ở kịch bản C | EC bị xoá, Attendance quay lại `Absent` |
| F | **Regression**: reason = `Work From Home` | Hành vi HRMS gốc không đổi (tạo Attendance status WFH, banner warnings vẫn chạy) |
| G | Nhập giờ trùng checkin đã có | Bị chặn với thông báo rõ ràng |
| H | Amend phiếu đã cancel | Không trỏ vào checkin cũ đã xoá (`no_copy`) |
| I | Ngày Chủ Nhật / ngày lễ | Dòng vẫn sinh, `existing_status` báo Holiday, engine tính OT CN đúng |
| J | Đo thời gian Submit | Ghi lại số giây thật → quyết định có cần chuyển sang background job không |

---

## 8. Ngoài phạm vi (nêu rõ, chưa làm)

- **Workflow duyệt + email thông báo quản lý.** Theo rule của dự án, không tự ý bật đường gửi mail
  nào; nếu cần thì làm riêng, `enabled = 0`, recipients rỗng, user tự chốt danh sách nhận.
- **Quyền submit của role `Employee`**: hiện `Employee` chỉ có create/write, **không có submit**.
  Giữ nguyên → nhân viên tạo draft, HR submit. Nếu muốn nhân viên tự submit thì phải bàn thêm
  (đụng đến kiểm soát công).
- **HRMS PWA / mobile** (`hrms:my_attendance_requests`): child table mới sẽ không hiển thị trên
  app mobile, chỉ dùng được trên Desk.
