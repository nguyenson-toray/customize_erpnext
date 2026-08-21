# Leave Application Override

> **Mục đích:** Override Leave Application của HRMS cho các quy tắc nghỉ phép riêng của TIQN.
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-12

**Last Updated:** 2026-02-05

## Tổng quan

Override HRMS Leave Application để hỗ trợ:
1. Validate attendance với logic mới (chỉ block Full Day + working_hours >= 8)
2. Attendance status logic: Half Day / Present / On Leave
3. 2 Half Day LAs riêng biệt cùng ngày (dual leave)

## Custom Fields (Attendance)

| Field | Type | Description |
|-------|------|-------------|
| `custom_leave_type_2` | Link (Leave Type) | Leave type của LA thứ 2 |
| `custom_leave_application_2` | Link (Leave Application) | LA thứ 2 |
| `custom_leave_application_abbreviation` | Data | Abbreviation (P/2, OP/2, etc.) |

## Configuration

```python
# leave_application.py
# Ngưỡng lấy từ Attendance Calculation Setting.full_day_leave_block_hours (mặc định 8),
# KHÔNG còn là hằng số. Xem leave_application.py:99.
full_day_block_hours = get_attendance_settings().full_day_leave_block_hours
```

## Attendance Status Logic

### validate_attendance()

| Leave Type | Working Hours | Kết quả |
|------------|---------------|---------|
| Half Day | Any | ✅ Cho phép |
| Full Day | < 8h | ✅ Cho phép |
| Full Day | >= 8h | ❌ Block |

### create_or_update_attendance()

| Leave Type | Has Check-in | Attendance Status |
|------------|--------------|-------------------|
| Half Day | Any | **Half Day** |
| Full Day | Yes (wh > 0) | **Present** |
| Full Day | No (wh = 0) | **On Leave** |

## Override Functions

### 1. `custom_validate_attendance()`

```python
# Logic mới
- Half Day leave: LUÔN cho phép
- Full Day leave + working_hours >= 8: BLOCK
- Full Day leave + working_hours < 8: Cho phép
```

### 2. `custom_create_or_update_attendance()`

Status logic:
```python
if is_half_day:
    status = "Half Day"
elif has_checkin:  # working_hours > 0 or in_time
    status = "Present"
else:
    status = "On Leave"
```

Hỗ trợ dual leave:
- LA1: `leave_type`, `leave_application`
- LA2: `custom_leave_type_2`, `custom_leave_application_2`

### 3. `on_leave_application_cancel()` (Hook)

Xử lý cancel khi có dual leave:
- LA1 cancel + LA2 exists → Swap LA2 → LA1
- LA2 cancel → Clear LA2 fields
- LA only → Let HRMS handle

## Abbreviation

| LA1 | LA2 | Display |
|-----|-----|---------|
| Sick | - | O/2 |
| Annual | - | P/2 |
| Sick | Annual | OP/2 |

## File liên quan

```
overrides/
├── leave_application/
│   ├── __init__.py              # Monkey patches
│   ├── leave_application.py     # Override functions
│   └── leave_application_override.md
└── leave_utils.py               # Helper functions
```

## Monkey Patches

```python
# __init__.py
LeaveApplication.validate_attendance = custom_validate_attendance
LeaveApplication.create_or_update_attendance = custom_create_or_update_attendance
```

## Doc Events (hooks.py)

```python
"Leave Application": {
    "on_cancel": "customize_erpnext.overrides.leave_application.leave_application.on_leave_application_cancel"
}
```

## Related: shift_type_optimized.py

`_core_process_attendance_logic_optimized()` cũng sử dụng cùng logic status:

```python
# Khi update attendance có leave
if old_status == 'Half Day':
    status = 'Half Day'
    # Nguồn duy nhất: overrides/leave_rules.resolve_half_day_status()
    half_day_status = resolve_half_day_status(has_checkin, other_leave_type)
elif old_status == 'On Leave':
    status = 'Present' if has_checkin else 'On Leave'
```


## ⚠ Quy tắc `half_day_status` và mã tổ hợp — đọc `leave_rules.py`

Từ 10/08/2026 mọi quyết định chuyển sang `overrides/leave_rules.py`, dùng chung với engine tính
công (`overrides/shift_type/shift_type_optimized.py`) vì engine **luôn ghi sau cùng**.

`half_day_status` **không** phụ thuộc "có checkin hay không" mà phụ thuộc **nửa còn lại có được
công ty trả lương hay không** — ca `OP/2` không có checkin nào vẫn là `Present`.

Mã tổ hợp là **bảng tra** theo quy định, không phải nối chuỗi: Ốm + Không lương (`KL`) ra
**`OK/2`**, không phải `OKL/2` cũng không phải `O/KL`.

Bảng đầy đủ + căn cứ: [`QUY_DINH_NGHI_PHEP_2025.md`](QUY_DINH_NGHI_PHEP_2025.md) mục 3.5 và 5.2.
Kiểm chứng: [`test_leave_rules.py`](test_leave_rules.py).


## Cách đặt tên đơn — `LA-YYYY-MM-#####`

Từ 20/08/2026, đơn **MỚI** mang tên `LA-2026-08-00001`, trong đó **`YYYY-MM` lấy từ `from_date`**
của đơn, không phải ngày tạo. Code: `CustomLeaveApplication.autoname()`.

**Vì sao không đổi naming series mà phải viết `autoname()` tay:** `.YYYY.` / `.MM.` của Frappe lấy
theo **ngày hôm nay**. Đơn nghỉ tháng 3 nhập vào tháng 8 sẽ mang số tháng 8 — sai với cách HR tra
cứu. Đã kiểm: `from_date = 2026-03-05` ra `LA-2026-03-00001` dù chạy trong tháng 8.

Mỗi tháng một **bộ đếm riêng**, bắt đầu từ `00001`.

⚠ **Chỉ áp cho đơn mới** — quy tắc không đổi tên hồi tố. Thực tế hiện tại **0 đơn** còn mang tên
`HR-LAP-…`, nhưng không phải vì đã đổi tên: toàn bộ đơn cũ đã được xoá và **import lại** ngày
20/08/2026, nên tất cả 7.096 đơn hiện có đều sinh tên mới qua `autoname()`. Nếu về sau còn đơn tên
cũ thì cứ để nguyên — đổi tên sẽ kéo theo hàng chục nghìn tham chiếu ở
`Attendance.leave_application` và `Leave Ledger Entry.transaction_name`.

⚠ Thứ tự trong `frappe/model/naming.py:set_new_name`: nhánh `amended_from` chạy **trước** rồi
`return`, sau đó mới `run_method("autoname")`, cuối cùng mới tới meta `naming_series:`. Nên:
bản **amend** vẫn ra `LA-2026-05-00001-1` và **không tiêu số** của bộ đếm; và Property Setter
`naming_series = 'HR-LAP-.YYYY.-'` **giữ nguyên** làm lưới an toàn — nếu module override không nạp
được thì đơn mới quay về tên cũ chứ không vỡ.

### 🔴 Bộ đếm `tabSeries` mất dòng = HR không tạo được đơn nghỉ nào nữa

Số kế tiếp của mỗi tháng nằm ở `tabSeries.current` với tiền tố `LA-YYYY-MM-`. Nếu **dòng đó biến
mất**, `getseries()` tưởng tháng đó chưa từng phát số và bắt đầu lại từ `00001` — đụng ngay tên đã
tồn tại:

```
DuplicateEntryError: ('Leave Application', 'LA-2026-03-00001', ...)
```

Đơn cũ vẫn nguyên vẹn, không mất dữ liệu, nhưng **mọi đơn mới đều lưu hỏng** cho tới khi dựng lại
bộ đếm. Triệu chứng dễ đổ nhầm cho phân quyền hoặc cho chính `autoname()`.

Hai đường làm mất dòng đếm:

1. **Xoá hết đơn của một tháng qua UI/ORM** — `revert_series_if_last()` lùi bộ đếm, về 0 thì xoá
   dòng. (`scripts/reset_leave_all.sql` xoá bằng SQL thuần nên **không** gây ra chuyện này.)
2. **Script dọn dẹp xoá thẳng `tabSeries`.** Đã xảy ra thật: bản đầu của
   `test_leave_application_naming.py` kết thúc bằng
   `delete from tabSeries where name like 'LA-%'` + `commit()`. Lúc viết, DB vừa bị xoá sạch nên
   chưa có đơn `LA-` nào và dòng lệnh đó vô hại. Sau khi import 7.096 đơn thật, **mỗi lần chạy test
   là một lần xoá sạch bộ đếm production**.

**Sửa:** chạy `scripts/repair_leave_application_series.sql` — dựng lại bộ đếm từ chính các bản ghi
đang có, idempotent, chỉ nâng chứ không hạ (`GREATEST`), không đụng bản ghi nào.

Kiểm thử: `test_leave_application_naming.py` — 14 assert, chỉ `rollback()` (bộ đếm nằm trong cùng
transaction nên tự về chỗ cũ). Các assert đều **tương đối** với bộ đếm đo được lúc bắt đầu, không
neo vào số tuyệt đối `00001` như bản đầu — nếu neo tuyệt đối thì test chỉ xanh khi bảng rỗng.
PHẦN 5 chụp lại toàn bộ `LA-*` trước/sau và **báo đỏ nếu test làm lệch bộ đếm**.
