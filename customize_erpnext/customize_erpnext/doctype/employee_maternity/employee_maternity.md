# Employee Maternity

> **Mục đích:** Doctype quản lý các giai đoạn thai sản của nhân viên.
> **Phạm vi:** DocType tự phát triển
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-17

Doctype quản lý các giai đoạn thai sản của nhân viên. Mỗi nhân viên 1 record cho 1 chu kỳ thai sản, chứa **cả 3 giai đoạn** dưới dạng 3 cặp ngày (không còn kiểu 1 record / 1 type như bản cũ).

## Cấu trúc field

| Field | Type | Mô tả |
|-------|------|-------|
| `employee` | Link → Employee | Nhân viên (reqd) |
| `full_name`, `group`, `designation`, `date_of_joining` | fetch | Fetch từ Employee |
| `status` | Select (read-only) | `Pregnant` / `Maternity Leave` / `Young Child` / `Inactive` / rỗng — **tự tính**, xem bên dưới |
| `apply_hour_reduction` | Check (default 1) | Áp dụng giảm 1 giờ làm việc (Apply Hour Reduction) |
| `pregnant_from_date` | Date | Bắt đầu thai kỳ (HR nhập) |
| `pregnant_to_date` | Date (read-only) | **Derived** |
| `estimated_due_date` | Date | Ngày dự sinh |
| `maternity_from_date` | Date | Bắt đầu nghỉ thai sản (thực tế) |
| `maternity_from_date_estimate` | Date | Bắt đầu nghỉ thai sản (dự kiến — fallback khi chưa có ngày thực tế) |
| `maternity_to_date` | Date | Kết thúc nghỉ thai sản |
| `date_of_birth` | Date | Ngày sinh con |
| `youg_child_from_date` | Date (read-only) | **Derived** |
| `youg_child_to_date` | Date (read-only) | **Derived** |
| `gestational_age` | Float (virtual) | Tuổi thai (tháng), clamp [0, 9.5] |
| `seniority` | Int (virtual) | Thâm niên (tháng) từ date_of_joining |

## Derived dates (server `calculate_derived_dates()` — mirror client JS)

`effective_mat_from = maternity_from_date || maternity_from_date_estimate`

| Field | Công thức |
|-------|-----------|
| `pregnant_to_date` | `effective_mat_from - 1 ngày` (fallback: `estimated_due_date`; không bao giờ bị clear) |
| `maternity_to_date` | `effective_mat_from + 6 tháng` (chỉ khi đang trống) |
| `youg_child_from_date` | `maternity_to_date + 1 ngày` |
| `youg_child_to_date` | `date_of_birth + 364 ngày` |

**Data Import:** giá trị import không bao giờ bị xóa — chỉ bị ghi đè khi có source field để derive (record legacy có thể import trực tiếp phase dates mà không có source fields).

## Status

`calculate_status()`: hôm nay rơi vào giai đoạn nào → status đó. Giai đoạn Maternity dùng `effective_mat_from` (fallback estimate). Nếu rơi vào nhiều giai đoạn (data legacy) → chọn giai đoạn có from_date muộn nhất. Qua hết `youg_child_to_date` → `Inactive`. Không rơi vào đâu → rỗng.

- **Tự tính lại hàng ngày** — scheduler cron 00:10: `scheduled_calculate_all_maternity_statuses()`
- **List view** có nút **Calculate Status** (tất cả hoặc records được chọn) và **Show Invalid Records** (tìm record có gap ≠ 1 ngày giữa các giai đoạn)

### 🔴 Nghỉ việc cắt hết mọi giai đoạn

`calculate_status()` kiểm tra nhân viên **trước** khi nhìn ngày tháng: đã nghỉ việc → `Inactive`,
kể cả khi `youg_child_to_date` còn ở tương lai. Ngày tháng trên record giữ nguyên (đó là lịch sử),
chỉ trạng thái là đóng.

⚠ **`relieving_date` là ngày BẮT ĐẦU nghỉ việc, không phải ngày làm cuối** — ngày làm cuối là
`relieving_date - 1`. Nên "còn làm tại ngày X" là `relieving_date > X` (xem `_has_left()`).

⚠ **Không dùng `Employee.status == 'Left'` làm điều kiện duy nhất.**
`auto_mark_employees_as_left` (00:00) chỉ quét người đang `Active`, mà người đang thai sản mang
status `Inactive` → tới ngày nghỉ việc họ **không** được đổi sang `Left`. `_has_left()` vì vậy ưu
tiên `relieving_date`, `status` chỉ là fallback. (Quyết định 26/08: **không** nới
`auto_mark_employees_as_left` ra cho `Inactive` — sửa ở phía maternity thôi. 17 Intern-000x đang
`Inactive` + quá hạn `relieving_date` vì vậy vẫn không bao giờ thành `Left`; cố ý không đụng.)

🔴 **`Employee.status` trên site này là `"Left "` — CÓ DẤU CÁCH ở cuối, 1.393 bản ghi.**
MySQL so sánh kiểu PAD SPACE nên `WHERE status = 'Left'` và `IN ('Active','Inactive')` vẫn đúng,
không ai phát hiện ra. Nhưng trong Python `"Left " == "Left"` là **False**. Mọi so sánh status
bằng Python phải `.strip()` (xem `_has_left`). Chỗ khác còn dính bẫy này:
`overrides/employee/employee.py::mark_employee_left` (hiện vô hại vì job đã lọc `status='Active'` ở SQL).

(Đoạn trên viết từ thời module còn lật `Employee.status`. Từ 04/09/2026 **không còn lật nữa** —
xem mục dưới. `_has_left()` vẫn ưu tiên `relieving_date` vì 17 Intern-000x vẫn mang `Inactive`.)

## 🔴 Không dùng `Employee.status = Inactive` cho thai sản (chốt 04/09/2026)

Trước đây `employee_status_sync.py` lật `Active → Inactive` khi vào kỳ nghỉ thai sản. **Đã bỏ
hẳn.** Thay bằng cờ chỉ-đọc `Employee.custom_is_maternity_leave`. Bốn lý do, đo trên chính site:

1. **Mất dữ liệu quẹt thẻ.** `hrms/hr/doctype/employee_checkin/employee_checkin.py:29` gọi
   `validate_active_employee()` → throw với `Inactive`. Máy chấm công đẩy dữ liệu qua API
   (64.226 bản ghi/tháng) sẽ lỗi. Mà chuyện "HR ghi sai ngày, nhân viên đi làm thật" **đang xảy
   ra**: 4 người / 66 lần quẹt rơi vào kỳ nghỉ thai sản.
2. **Engine tính công bỏ qua** — `shift_type_optimized.py` chỉ lấy `Active` hoặc `Left`.
3. **Export Excel bỏ qua** — `standard_export.py` cùng điều kiện.
4. **Leave Control Panel bỏ qua** — HRMS lọc `Active`, nên không cấp phép năm, trong khi Điều 65
   NĐ 145/2020 vẫn tính thời gian nghỉ thai sản là thời gian làm việc để hưởng phép năm.

Và `status` là field hàng chục luồng khác cùng ghi: **25/08/2026 một thao tác cập nhật Employee
hàng loạt đã ghi đè 34 người vừa lật sang `Inactive` về lại `Active`** (xem Comment audit
`"Status Active → Inactive — Maternity phase …"`, 34 dòng từ 17/08 đến 26/08), và cơ chế cũ chỉ
chạy khi CÓ CHUYỂN TIẾP nên không lần nào sửa lại.

### Cờ `custom_is_maternity_leave`

| | |
|---|---|
| Kiểu | `Check`, `read_only`, `in_standard_filter` — **cột thật** trong `tabEmployee` |
| Nguồn | `Employee Maternity.status == "Maternity Leave"`, **không** phải khoảng ngày |
| Ghi bởi | job 00:10 (`sync_all_maternity_flags`, khẳng định lại TOÀN BỘ), `on_update`, `on_trash` |

🔴 **Nguồn phải là `status`, không phải khoảng ngày.** `api/headcount.py::maternity_leave_employees()`
— thứ quyết định Net Headcount trên dashboard và daily email — cũng đọc `status`. Đo 04/09/2026:
28 record có khoảng ngày phủ hôm nay nhưng chỉ **27** mang status `Maternity Leave` (cái lệch
thuộc người đã nghỉ việc, record đã đóng thành `Inactive`). Lấy khác nguồn là hai con số lệch nhau
mà không ai truy được vì sao.

🔴 **Cờ chỉ mang nghĩa HÔM NAY.** Mọi thứ tính theo kỳ (engine, Export Excel, báo cáo tháng) vẫn
phải đọc `maternity_from_date..maternity_to_date`. Join vào cờ này là xuất báo cáo tháng 3 vào
tháng 9 sẽ ra sai.

Vì sao cần **cột thật** trong khi `Employee Maternity.status` đã có sẵn thông tin: Number Card và
Dashboard Chart kiểu "Document Type" chỉ lọc được field nằm trên **chính doctype** của chúng,
không join sang doctype khác. Không có cột này thì 7 chart/card đếm nhân viên của hrms (Total
Employees, Department Wise Employee Count, Gender Diversity Ratio, Employees by Branch/Type/Grade,
Designation Wise Employee Count) không có cách nào trừ người đang nghỉ thai sản.

⚠ **Chưa đụng 7 chart/card đó** (chốt 04/09/2026: không sửa bản gốc của hrms vì `is_standard = 1`
+ module HR ⇒ `bench migrate` sync lại từ file app và lật ngược mọi sửa đổi trên UI). Cái nào cần
thì tạo mới rồi override sau. Sai lệch hiện tại: 27/1.042 ≈ 2,6%.

`is_inactive_for_maternity()` giữ lại làm lưới an toàn cho `Employee.update_user_status()`: nếu HR
tự tay set `Inactive` cho người đang nghỉ thai sản thì User liên kết vẫn không bị khoá.

Đo trên site 26/08/2026: **36/250 record** đang mở cho người đã nghỉ việc (4 `Maternity Leave`,
18 `Young Child`, 14 rỗng) — record cũ nhất từ 2023. **Đã chạy Calculate Status trên production
26/08**, giờ còn 0; chạy lại batch trả `{updated: 0, closed_for_left: 0}`.

### Filter `Employee Status` trên report (thêm 26/08/2026)

`Employee Maternity Report` trước đây không lọc `Employee.status` → hiện cả người đã nghỉ việc
như đang hưởng chế độ, lệch với number card. Đã thêm filter `employee_status`
(MultiSelectList, **mặc định `["Active", "Inactive"]`**).

⚠ Mặc định **phải có `Inactive`**: người đang nghỉ thai sản mang `Employee.status = Inactive`,
bỏ nó ra là giấu đúng nhóm mà report sinh ra để theo dõi. Đây cũng đúng bộ
`api/headcount.py::MATERNITY_EMPLOYEE_STATUSES`. Để trống filter = lấy tất cả (xem lịch sử).

Đo 26/08/2026 với `maternity_type = Maternity Leave` + `status = Active`:

| | Số NV |
|---|---|
| Report, không lọc `employee_status` | 32 |
| Report, mặc định `Active + Inactive` | **28** |
| Number card HR Overview | **28** |

Hai tập **trùng khít** — `report - card` và `card - report` đều rỗng.

## Đồng bộ sang Employee.status (`employee_status_sync.py`)

Chỉ `Maternity Leave` là nghỉ thật. `Pregnant` và `Young Child` vẫn đi làm bình
thường (chỉ hưởng chế độ về sớm 1 giờ) nên employee giữ `Active`.

| Chuyển tiếp status của record | `Employee.status` |
|---|---|
| `* → Maternity Leave` | `Inactive` |
| `Maternity Leave → *` | `Active` |
| còn lại | không đụng |

**4 guard rail — đừng bỏ khi refactor:**

1. **Chỉ chạy khi có chuyển tiếp** (`old != new`). Scheduler quét lại toàn bộ record
   mỗi ngày; nếu khẳng định lại status ở trạng thái ổn định thì sẽ ghi đè thay đổi
   thủ công của HR.
2. **Chỉ lật `Active` ⇄ `Inactive`.** `Left` / `Suspended` là quyết định nhân sự vì
   lý do khác — không bao giờ ghi đè.
3. **Trước khi trả về `Active`**, kiểm tra không còn record maternity nào KHÁC của
   employee đó đang `Maternity Leave` (một nhân viên có thể có 2–3 chu kỳ).
4. **Ghi bằng `frappe.db.set_value`**, không `doc.save()` — lifecycle của Employee
   clear cache toàn site và disable User trên mỗi lần save.

**3 điểm gọi** (thiếu 1 là sync coi như hỏng):

| Điểm | Vì sao |
|---|---|
| `on_maternity_update` | HR save trên UI / Data Import. Có xử lý đổi employee: employee CŨ được trả về Active |
| `calculate_all_maternity_statuses()` | Dùng `db_set(update_modified=False)` → **bypass hook**, phải gọi tay. Đây là đường của scheduler 00:00 + nút Calculate Status, tức là nơi hầu hết chuyển tiếp thật xảy ra. Tra `Employee.relieving_date/status` một lần cho cả lô rồi truyền xuống `calculate_status(employment=...)` |
| `on_maternity_delete` | Xoá record = giai đoạn biến mất |

Mỗi lần lật đều ghi 1 Comment trên Employee (`Status Active → Inactive — Maternity phase ...`).

### Employee.custom_sub_status — CHỈ HIỂN THỊ

Fieldtype **HTML** → **không có cột trong DB**, không lưu gì. `get_employee_sub_status()`
suy ra tại chỗ mỗi lần mở form; `employee.js::render_sub_status()` vẽ badge + link
tới record. Vì không lưu nên **không filter / report theo sub-status được**.

`get_current_maternity_record()` chọn record "hiện hành" **xác định** — ưu tiên
`Maternity Leave` → `Pregnant` → `Young Child` → `Inactive`, đồng hạng thì lấy ngày
bắt đầu giai đoạn muộn nhất, rồi `modified`. Đừng thay bằng `LIMIT 1` trần: 18 nhân
viên đang có 2–3 record.

### Hệ quả đã biết của việc thành Inactive

- **Không còn được tính Attendance** — engine (`shift_type_optimized.py:1652`) chỉ lấy
  `Active` + `Left`. Đây là **cố ý**: người đang nghỉ thai sản không cần bản ghi công.
- **User không bị khoá** — `overrides/employee/employee_override.py::CustomEmployee`
  chặn `update_user_status()` của core. Class này kế thừa `EmployeeMaster` của HRMS
  (HRMS cũng chiếm `override_doctype_class["Employee"]`), đừng kế thừa thẳng core.
- **Card HR Overview** — `maternity_leave()` phải đếm cả `Inactive` nếu không sẽ về 0;
  `net_headcount()` vẫn chỉ trừ người còn `Active` (nếu nới ra `Inactive` sẽ trừ 2 lần).
- **Chưa xử lý:** Labor Contract (3 chỗ chặn `status != Active`), Uniform, Self-Update,
  Employee Photos, biometric_sync, daily_attendance_metrics — các module này sẽ bỏ qua
  người đang nghỉ thai sản.

## Validation

- Mỗi cặp: `from <= to` (cho phép phase 1 ngày)
- 3 giai đoạn không được overlap trong cùng record; giai đoạn thiếu to_date được coi là open-ended (vô hạn) khi check overlap

## Ảnh hưởng đến Attendance

**Gated by Attendance Calculation Setting → "Recalc Attendance on Maternity Save/Delete"** (`recalc_attendance_on_maternity_change`, mặc định **OFF**). Khi OFF, attendance chỉ được cập nhật ở lần chạy full kế tiếp hoặc Bulk Update thủ công.

Khi ON, mỗi lần tạo/sửa/xóa record:

1. `before_save` so sánh old vs new → thu thập các ngày bị ảnh hưởng theo employee (đổi employee → recalc cho **cả** employee cũ và mới)
2. Giới hạn đến hôm nay và `relieving_date - 1`
3. `on_update` / `on_trash` → queue background job (`enqueue_after_commit=True`, queue long) gọi `_core_process_attendance_logic_optimized()` cho đúng những ngày đó
4. Job skip nếu đang giờ cao điểm check-in/out (`is_peak_time()`) — lần chạy full kế tiếp bù

Lưu ý: Frappe chạy `on_update` sau **cả insert lẫn save** → không đăng ký hook `after_insert` (sẽ bị queue đôi).

### Hour Reduction trong Attendance

- Attendance field `custom_hour_reduction` = 1 khi employee có benefit → **giảm 1 giờ** khỏi standard working hours
- Benefit theo giai đoạn (dựa trên ngày attendance rơi vào cặp from/to nào):
  - `Maternity Leave`, `Young Child`: luôn benefit
  - `Pregnant`: chỉ khi `apply_hour_reduction = 1`

### Các nơi đọc Employee Maternity

| File | Mô tả |
|------|-------|
| `overrides/shift_type/shift_type_optimized.py` | `check_maternity_status_cached()` + preload — tính attendance |
| `api/employee/employee_utils.py` | `check_employee_maternity_status()` |
| `overrides/attendance/attendance.py` | Info hiển thị trên Attendance form |
| `customize_erpnext/report/employee_maternity_report/` | Report thai sản |
| `customize_erpnext/report/shift_attendance_customize/` | Report + scheduler + standard export |
| `health_check_up/doctype/health_check_up/` | Xác định pregnant theo khoảng ngày khi khám sức khỏe |

## Hooks (hooks.py)

```python
"Employee Maternity": {
    "on_update": "...employee_maternity.on_maternity_update",   # chạy sau cả insert lẫn save
    "on_trash":  "...employee_maternity.on_maternity_delete",
}

# Scheduler: daily 00:10 — PHẢI sau auto_mark_employees_as_left (00:00),
# để người vừa tới ngày nghỉ việc đã mang status Left khi job này quét qua.
"10 0 * * *": ["...employee_maternity.scheduled_calculate_all_maternity_statuses"]
```

(Không còn LA → Employee Maternity auto-sync; record do HR quản lý thủ công / Data Import.)

## API

### `get_employee_maternity_for_excel` (Power Query / Excel)

`@frappe.whitelist()` — **yêu cầu đăng nhập hoặc API key** (`Authorization: token <api_key>:<api_secret>`). Không mở `allow_guest` vì dữ liệu thai sản nhạy cảm.

Params: `employee`, `status`, `group`, `page`, `page_size` (0 = all), `lang` (`en`/`vi`).
Trả về `{ data, columns, col_keys, total, page, page_size, total_pages }` kèm 2 virtual field `gestational_age`, `seniority`.

### `calculate_all_maternity_statuses(names=None)`

Batch recalc status (dùng bởi nút list view + scheduler). `names=None` → tất cả.
Trả `{updated, total, closed_for_left}` — `closed_for_left` đếm riêng số record đóng vì nhân viên
đã nghỉ việc (nhóm này không tự đóng theo ngày tháng).

### `get_invalid_maternity_records()`

Tìm record có gap giữa các giai đoạn ≠ 1 ngày (dùng bởi nút "Show Invalid Records").
