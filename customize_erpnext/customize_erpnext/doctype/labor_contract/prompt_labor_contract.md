# Prompt cho Claude Code: Triển khai chức năng "Labor Contract" (quản lý hạn hợp đồng lao động & cảnh báo) trong Frappe HRMS

## 0. Yêu cầu bắt buộc trước khi bắt đầu

Trước khi viết bất kỳ dòng code nào, **đọc toàn bộ tài liệu tại `/home/frappe/frappe-bench/.claude/skills/erpnext-frappe/references`** và tuân thủ mọi quy ước, convention, cấu trúc app đã quy định trong đó (naming convention, cách tổ chức doctype/controller, cách viết patch, cách viết hooks.py, coding style...). Nếu có xung đột giữa spec dưới đây và quy ước trong skill, **ưu tiên theo skill**, chỉ hỏi lại nếu xung đột ảnh hưởng tới logic nghiệp vụ cốt lõi.

Phạm vi công việc: **chỉ tập trung vào quản lý hạn hợp đồng lao động và cảnh báo sắp hết hạn**. Không làm phần nội dung/in ấn hợp đồng, không làm mail merge, không làm phần lương/salary structure.

---

## 1. Bối cảnh nghiệp vụ

Công ty áp dụng chuỗi hợp đồng lao động theo thứ tự cố định, không được nhảy cóc, không được có khoảng trống (gap) giữa các giai đoạn:

1. `30 days probationary contract` — thử việc 30 ngày
2. `60 days probationary contract` — thử việc 60 ngày
3. `1 year employment contract` — HĐLĐ 1 năm
4. `3 years employment contract` — HĐLĐ 3 năm
5. `Indefinite-term employment contract` — HĐLĐ không xác định thời hạn (điểm dừng cuối chuỗi, không có giai đoạn tiếp theo)

Lưu ý: nhân viên chỉ đi qua **một trong hai** loại thử việc (30 hoặc 60 ngày, tuỳ chức danh), không đi qua cả hai. Sau khi hoàn tất thử việc (loại nào cũng vậy), giai đoạn tiếp theo luôn là `1 year employment contract`.

---

## 2. Data model

### 2.1. Employment Type (doctype có sẵn của Frappe HRMS — chỉ thêm field, không tạo mới)

Đã có sẵn 5 record đúng theo danh sách ở mục 1 (nếu chưa có, cần tạo qua patch/fixture). Thêm 2 custom field:

| Fieldname | Label | Type | Ghi chú |
|---|---|---|---|
| `custom_period` | Contract Period (Days) | Int | Số ngày hiệu lực của loại hợp đồng này. Để **trống/0** với `Indefinite-term employment contract`. |
| `custom_warning_before` | Warning Before (Days) | Int | Số ngày cảnh báo trước khi hết hạn. Để **trống/0** với `Indefinite-term employment contract`. |

Giá trị đã có sẵn:

| Employment Type | custom_period | custom_warning_before |
|---|---:|---:|
| 30 days probationary contract | 30 | 7 |
| 60 days probationary contract | 60 | 7 |
| 1 year employment contract | 365 | 30 |
| 3 years employment contract | 1095 | 30 |
| Indefinite-term employment contract | (trống hoặc 0) | (trống hoặc 0) |

### 2.2. Employee (doctype có sẵn — đã có sẵn từ trước, KHÔNG cần đụng tới)

Các field sau **đã tồn tại sẵn**, không cần tạo lại, chỉ cần biết để dùng trong logic:
- `Designation.custom_probation_days` (Select: 30/60) — xác định chức danh áp dụng thử việc bao nhiêu ngày.
- `Employee.custom_probation_days` — fetch_from Designation, dùng để suy ra Employment Type thử việc tương ứng (30 → `30 days probationary contract`, 60 → `60 days probationary contract`).
- `Employee.date_of_joining`, `Employee.status`, `Employee.designation` — dùng trong logic bên dưới.

### 2.3. Labor Contract (**doctype mới**, cần tạo)

Mỗi record = **1 lần ký hợp đồng** (không gộp nhiều giai đoạn vào 1 record/nhân viên).

| Fieldname | Label | Type | Ghi chú |
|---|---|---|---|
| `employee` | Employee | Link → Employee | Bắt buộc |
| `employee_name` | Employee Name | Data | fetch_from `employee.employee_name`, read-only |
| `designation` | Designation | Link → Designation | fetch_from `employee.designation`, read-only |
| `department` | Department | Link → Department | fetch_from `employee.department`, read-only |
| `contract_type` | Contract Type | Link → Employment Type | Bắt buộc, loại của **chính giai đoạn này** |
| `start_date` | Start Date | Date | Bắt buộc |
| `end_date` | End Date | Date | Trống nếu `contract_type` = Indefinite-term |
| `next_contract_type` | Next Contract Type | Link → Employment Type | Read-only, tính tự động. Trống nếu `contract_type` hiện tại đã là Indefinite-term |
| `next_sign_date` | Next Sign Date | Date | Read-only, = `end_date + 1 ngày`. Trống tương ứng |
| `status` | Status | Select: `Upcoming`, `Signed`, `Overdue` | Bắt buộc, default `Upcoming` |
| `next_stage_created` | (ẩn khỏi form, dùng nội bộ) | Check | Cờ chống job tạo trùng record kế tiếp |
| `custom_section` | Section | Link → Section | Doctype "Section" đã có sẵn trong hệ thống (cùng nhóm với Department). Thông tin bổ sung, không có logic tự động — chỉ hiển thị/nhập tay, không tính toán gì thêm |
| `custom_group` | Group | Link → Group | Doctype "Group" đã có sẵn trong hệ thống (cùng nhóm với Department). Thông tin bổ sung, không có logic tự động — chỉ hiển thị/nhập tay, không tính toán gì thêm |

Gợi ý autoname: naming series dạng `LC-[employee]-#` 

Thêm liên kết vào panel **Connections** của Employee doctype để từ trang Employee xem được toàn bộ Labor Contract liên quan (Frappe tự làm việc này khi có Link field `employee` trỏ tới Employee — chỉ cần khai báo đúng, không cần code thêm).

---

## 3. Logic nghiệp vụ chi tiết

### 3.1. Hằng số dùng trong code

```python
# Thứ tự chuỗi cố định — dùng để tra "giai đoạn kế tiếp"
SEQUENCE = [
    "30 days probationary contract",
    "60 days probationary contract",
    "1 year employment contract",
    "3 years employment contract",
    "Indefinite-term employment contract",
]

# Từ 1 loại thử việc, giai đoạn kế tiếp luôn là "1 year employment contract"
# (không dùng SEQUENCE[index+1] cho 2 loại thử việc vì chúng không nối tiếp nhau)
def get_next_contract_type(current_type: str) -> str | None:
    if current_type in ("30 days probationary contract", "60 days probationary contract"):
        return "1 year employment contract"
    if current_type == "1 year employment contract":
        return "3 years employment contract"
    if current_type == "3 years employment contract":
        return "Indefinite-term employment contract"
    if current_type == "Indefinite-term employment contract":
        return None
    return None
```

### 3.2. Công thức tính ngày

Cho 1 record Labor Contract với `contract_type` và `start_date` đã biết:

```python
et = frappe.db.get_value(
    "Employment Type", contract_type,
    ["custom_period", "custom_warning_before"], as_dict=True
)

if et.custom_period:
    end_date = frappe.utils.add_days(start_date, et.custom_period - 1)  # bao trọn đủ số ngày, không lệch dư 1 ngày
else:
    end_date = None  # Indefinite-term

next_type = get_next_contract_type(contract_type)
next_sign_date = frappe.utils.add_days(end_date, 1) if (end_date and next_type) else None
```

### 3.3. Trigger A — Employee mới → tự tạo Labor Contract thử việc đầu tiên

Hook: `doc_events["Employee"]["after_insert"]` trong `hooks.py`.

Logic:
1. Nếu `frappe.flags.in_import` là True → **bỏ qua hoàn toàn** (tránh tự tạo sai khi migrate/import nhân viên cũ hàng loạt).
2. Nếu `Employee.custom_probation_days` rỗng → `frappe.msgprint(..., alert=True, indicator="orange")` báo HR tự tạo Labor Contract tay, **không tạo record**.
3. Ngược lại:
   - `contract_type` = `"30 days probationary contract"` nếu `custom_probation_days == 30`, hoặc `"60 days probationary contract"` nếu `== 60`.
   - `start_date` = `Employee.date_of_joining`.
   - Tính `end_date`, `next_contract_type`, `next_sign_date` theo công thức mục 3.2.
   - `status = "Upcoming"`.
   - Insert record Labor Contract mới.

### 3.4. Trigger B — Scheduled job chạy hàng ngày (daily)

Đăng ký trong `hooks.py` → `scheduler_events["daily"]`. Job làm 2 việc, theo đúng thứ tự:

**Bước 1 — Materialize giai đoạn kế tiếp:**

Query các Labor Contract thoả:
- `status = "Signed"`
- `next_stage_created = 0`
- `next_contract_type` không rỗng (tức chưa phải Indefinite-term)
- `employee.status = "Active"` (join qua Employee)
- `frappe.utils.date_diff(end_date, today()) <= custom_warning_before` (lấy `custom_warning_before` từ **Employment Type của `contract_type` hiện tại** của chính record này)

Với mỗi record thoả điều kiện:
- Tạo Labor Contract mới: `contract_type = next_contract_type` (của record cũ), `start_date = add_days(end_date, 1)` (của record cũ), tính `end_date/next_contract_type/next_sign_date` mới theo công thức 3.2, `status = "Upcoming"`.
- Set `next_stage_created = 1` trên record cũ (để job không tạo trùng ở lần chạy sau).

**Bước 2 — Chuyển Overdue:**

Query các Labor Contract thoả:
- `status = "Upcoming"`
- `start_date < today()`

→ set `status = "Overdue"`.

*(Lưu ý thứ tự: chạy Bước 1 trước Bước 2 trong cùng 1 lần job để tránh 1 record vừa mới materialize hôm nay bị đánh Overdue oan nếu `start_date` trùng hôm nay.)*

### 3.5. Đánh dấu Signed

Không cần code riêng — dùng **bulk edit có sẵn trên List View** của Labor Contract (chọn nhiều dòng → Edit → set `status = Signed`). Đảm bảo field `status` được khai báo `in_list_view: 1` và cho phép bulk edit (mặc định Frappe đã hỗ trợ, không cần cấu hình thêm).

### 3.6. Cảnh báo qua Notification

Tạo 1 **Notification** (Email Alert) trên doctype `Labor Contract`:
- Event: `New`
- Condition: `doc.status == "Upcoming"`
- Recipients: Role "HR Manager" (hoặc role tương ứng đang dùng trong hệ thống) + field `reports_to` của Employee liên quan (nếu cần lookup qua Employee, dùng "Recipients by Document Field" trỏ qua `employee.reports_to`, hoặc viết Recipients bằng Jinja nếu Notification hỗ trợ).
- Subject/Message: nêu tên nhân viên, loại hợp đồng, ngày cần ký (`next_sign_date` của record trước đó / `start_date` của record Upcoming vừa tạo).

Không cần thêm Notification "Days Before" nào khác — vì thời điểm tạo record Upcoming (mục 3.4 Bước 1) đã chính là thời điểm cần cảnh báo, dùng chung 1 cơ chế.

### 3.7. Nghỉ việc

- Job ở mục 3.4 **luôn lọc `employee.status = "Active"`** ở Bước 1 → nhân viên đã nghỉ (`Left`) sẽ không bao giờ được materialize giai đoạn tiếp theo.
- Không cần thêm logic gì khác cho case nghỉ việc trong phạm vi lần triển khai này.
- **Không xử lý case rehire** (status Left → Active lại) — để ngoài phạm vi, HR xử lý tay nếu phát sinh.

---

## 4. Việc KHÔNG cần làm (ngoài phạm vi)

- Không làm nội dung/in hợp đồng, không làm mail merge.
- Không validate chặn HR tự tạo/sửa tay Labor Contract trái chuỗi (để linh hoạt cho case đặc biệt), **trừ khi** skill reference có quy ước khác — nếu vậy làm theo skill.
- Không xử lý rehire.
- Không đổi field `Designation.custom_probation_days` hay `Employee.custom_probation_days` — giữ nguyên as-is.

---

## 5. Deliverables mong muốn

1. DocType `Labor Contract` (json + controller `.py`) đúng field spec mục 2.3.
2. Custom Field `custom_period`, `custom_warning_before` trên Employment Type (qua fixture hoặc patch, theo convention của skill).
3. Patch/fixture seed đủ 5 record Employment Type với giá trị đúng bảng mục 2.1 (tạo mới nếu chưa có, update nếu đã có).
4. Hook `after_insert` cho Employee (mục 3.3), đặt trong module phù hợp theo cấu trúc app hiện có.
5. Scheduled job daily (mục 3.4), đăng ký trong `hooks.py`.
6. Notification config (mục 3.6) — tạo qua fixture nếu convention của skill dùng fixture cho Notification, hoặc note lại các bước cấu hình tay nếu convention yêu cầu làm qua UI.
7. Basic test (theo chuẩn testing của skill reference nếu có) cho: (a) tạo Employee mới ra đúng Labor Contract thử việc, (b) job materialize đúng threshold, (c) job chuyển Overdue đúng điều kiện.
8. README ngắn mô tả lại luồng nghiệp vụ này để bàn giao (có thể gộp trong docstring/module doc thay vì file riêng nếu skill quy định vậy).

Nếu có bất kỳ điểm nào trong spec trên xung đột với cấu trúc app/module hiện tại đang có trong bench, hãy hỏi lại trước khi code thay vì tự suy đoán.
