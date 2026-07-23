# Monkey Patch Overrides — Hướng dẫn

Thư mục `overrides/` chứa các **monkey patch**: thay thế hàm/method của Frappe, ERPNext, HRMS
bằng bản custom mà **không** sửa code core (không đụng `apps/hrms`, `apps/erpnext`,
`apps/frappe`). Nhờ vậy `bench update` không ghi đè, và mọi tùy biến nằm gọn trong
`customize_erpnext`.

---

## 1. Cơ chế nạp (loading chain)

Patch được áp dụng **ngay khi app import**, cho MỌI context (web, worker/scheduler,
console, background job):

```
customize_erpnext/__init__.py
    └─ import customize_erpnext.overrides          # chạy khi app load
         └─ overrides/__init__.py                  # import từng module patch
              ├─ import ...overrides.employee_checkin      → chạy employee_checkin/__init__.py
              ├─ import ...overrides.shift_type            → chạy shift_type/__init__.py
              ├─ import ...overrides.attendance            → chạy attendance/__init__.py
              ├─ import ...overrides.leave_application
              ├─ import ...overrides.earned_leave
              └─ import ...overrides.employees_by_age
```

Mỗi `overrides/<name>/__init__.py` khi được import sẽ **thực thi câu lệnh gán** thay thế
hàm/method core → patch có hiệu lực.

---

## 2. ⚠️ GOTCHA quan trọng (bug đã dính 2026-07-23)

> **Tạo file patch thôi là CHƯA đủ.** Nếu không thêm dòng `import` vào
> `overrides/__init__.py`, module patch **không bao giờ chạy** → patch âm thầm vô hiệu,
> không báo lỗi.

Sự cố: `overrides/employees_by_age/__init__.py` tồn tại và đúng, nhưng thiếu dòng
`import customize_erpnext.overrides.employees_by_age` trong `overrides/__init__.py`.
Kết quả: chart "Employees by Age" vẫn dùng range mặc định hrms (15–79, 80+) thay vì
custom (18–47, 48+) — không lỗi, chỉ là patch không áp.

**Checklist khi thêm override mới:** phải sửa **2 file** — file patch mới **và**
`overrides/__init__.py`.

---

## 3. Hai kiểu patch

### Kiểu A — Thay hàm module-level

Dùng khi core gọi hàm qua **tên module** (vd `get_ranges()` trong cùng module gọi
`get_data`). Gán lại thuộc tính của module core.

```python
# overrides/employees_by_age/__init__.py
import hrms.hr.dashboard_chart_source.employees_by_age.employees_by_age as hrms_mod
from customize_erpnext.overrides.employees_by_age.employees_by_age import custom_get_ranges

# Lưu bản gốc để rollback/debug (chỉ lưu 1 lần, tránh lưu đè bản đã patch)
if not hasattr(hrms_mod, "_original_get_ranges"):
    hrms_mod._original_get_ranges = hrms_mod.get_ranges

hrms_mod.get_ranges = custom_get_ranges     # ← patch
```

Điều kiện để kiểu A ăn: hàm core gọi tên đó qua **global lookup lúc runtime**
(vd `ranges = get_ranges()` bên trong `get_data`). Nếu core đã `from x import get_ranges`
vào biến cục bộ thì patch module KHÔNG ăn — phải patch nơi biến đó sống.

### Kiểu B — Thay method của class

Gán lại method trên class core.

```python
# overrides/attendance/__init__.py
from hrms.hr.doctype.attendance.attendance import Attendance
from customize_erpnext.overrides.attendance.attendance import custom_attendance_validate

Attendance.validate = custom_attendance_validate    # ← patch, self là doc
```

Method custom nhận `self` là document. Ví dụ khác:
`hrms_st.ShiftType.get_employee_checkins = custom_...`,
`LeaveApplication.validate_attendance = custom_...`.

---

## 4. Cách thêm một override mới (step-by-step)

1. Tạo thư mục `overrides/<name>/` với:
   - `__init__.py` — chứa câu lệnh **gán patch** (kiểu A hoặc B ở trên).
   - `<name>.py` — chứa hàm/method custom (`custom_...`).
2. Viết hàm custom trong `<name>.py`. Giữ **cùng signature** với bản core.
   Nếu chỉ đổi một nhánh, có thể gọi lại `_original_...` cho phần còn lại.
3. **BẮT BUỘC**: thêm vào `overrides/__init__.py` (trong khối `try`):
   ```python
   import customize_erpnext.overrides.<name>
   ```
4. `bench restart` (xem mục 5) rồi verify (mục 6).

Ví dụ khung `<name>.py`:
```python
import frappe

def custom_something(self, *args, **kwargs):
    # ... logic custom ...
    # (tùy chọn) gọi lại bản gốc: self._original_something(*args, **kwargs)
    return ...
```

---

## 5. Restart — thay đổi Python PHẢI restart

Monkey patch là code Python → sửa xong **không** tự nạp lại. Tùy patch chạy ở đâu:

| Patch ảnh hưởng | Cần restart |
|---|---|
| Web/desk (form, dashboard chart, report) | `frappe-bench-web:frappe-bench-frappe-web` |
| Scheduler / background job (vd auto-attendance ban đêm) | `frappe-bench-workers:` |
| Cả hai (an toàn nhất) | cả hai group |

```bash
sudo supervisorctl restart frappe-bench-web:frappe-bench-frappe-web frappe-bench-workers:
bench --site erp.tiqn.local clear-cache
```

> Bài học: từng backfill/sửa mà chỉ restart **web**, quên **workers** → scheduler ban
> đêm vẫn chạy code cũ. Nếu patch động tới job nền, PHẢI restart workers.

`bench console` là tiến trình mới nên luôn thấy code mới — **không** phản ánh việc worker
đang chạy có được patch hay chưa. Đừng dùng console để kết luận "patch đã ăn trên production".

---

## 6. Verify / debug

Kiểm tra một patch đã áp chưa (trong `bench console`):
```python
import customize_erpnext.overrides            # nạp toàn bộ patch
import hrms.hr.dashboard_chart_source.employees_by_age.employees_by_age as m
print(m.get_ranges.__name__)                  # 'custom_get_ranges' nếu đã patch
```

- Bản gốc luôn được giữ ở `_original_<name>` để so sánh / rollback.
- Lỗi khi nạp patch được nuốt trong `try/except` ở `overrides/__init__.py` và ghi vào
  **Error Log** ("Overrides Import Error") — kiểm tra đó nếu nghi patch không nạp.
- Log thành công: `✅ All overrides loaded successfully (on import)`.

---

## 7. Danh sách override hiện có

| Thư mục | Patch gì | Kiểu |
|---|---|---|
| `employee_checkin/` | `create_or_update_attendance` (tính công/OT, tạo Attendance) | A |
| `shift_type/` | `ShiftType.get_employee_checkins`, `should_mark_attendance`, auto-attendance | B |
| `attendance/` | `Attendance.validate` (thêm status Maternity Leave, stamp section/group) | B |
| `leave_application/` | `LeaveApplication.validate_attendance`, `create_or_update_attendance` | B |
| `earned_leave/` | cấu hình/nghiệp vụ Earned Leave (nhiều hàm hr_utils + LeavePolicyAssignment) | A/B |
| `employees_by_age/` | `get_ranges` cho dashboard chart "Employees by Age" (18–47, 48+) | A |

Các file `.py` phụ (không phải thư mục patch): `leave_utils.py` (helper dùng chung).
Các `.md` khác: `override_attendance_shift_checkin.md`, `item_stock_customize*.md` — ghi chú
nghiệp vụ chi tiết theo mảng.
