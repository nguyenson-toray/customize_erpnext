# PROJECT: Employee Onboarding Form — Self-Service

## Bối cảnh

Công ty sử dụng **Frappe HRMS**. Employee được HR nhập thủ công (không qua tuyển dụng trên hệ thống). Cần một giải pháp để nhân viên mới **tự nhập thông tin cá nhân** mà không cần tài khoản hệ thống.

> **BẮT BUỘC**: Đọc skill & reference tại `/home/frappe/frappe-bench/.claude/skills` trước khi triển khai. Tuân thủ pattern, coding convention và API reference trong đó.

---

## Tổng quan luồng hoạt động

```
HR tạo Employee (tên, DOB, date_of_joining, số điện thoại)
        │
        ▼
HR vào Employee Onboarding Settings → cấu hình bộ lọc (theo ngày / chọn thủ công)
        │
        ▼
Nhân viên mới quét QR cố định hoặc QR riêng (theo mã NV) → mở Web Page (KHÔNG cần login)
        │
        ▼
Chọn tên mình (dropdown) hoặc tự động xác định (nếu QR theo mã NV) → Nhập SĐT xác thực
        │
        ▼
Nhập form thông tin cá nhân (địa chỉ, ngân hàng, ...) → Lưu
        │
        ▼
HR review → Approve / Reject → Sync sang Employee
```

---

## Phần 1: Custom Doctype — `Employee Onboarding Form`

### Mục đích
Lưu thông tin do nhân viên mới tự nhập, chờ HR review & đồng bộ sang Employee.

### Doctype config
- **is_submittable = False** — chỉ cần Save, không dùng Submit workflow của Frappe.
- Trạng thái quản lý bằng field `status` (Select), không dùng docstatus.

### Các field gợi ý

| Field              | Type          | Ghi chú                                    |
| ------------------ | ------------- | ------------------------------------------- |
| `employee`         | Link/Employee | Bắt buộc — link đến Employee đã tạo sẵn    |
| `employee_name`    | Data          | Fetch from Employee                         |
| `date_of_joining`  | Date          | Fetch from Employee                         |
| `cell_number`      | Data          | Fetch from Employee                         |
| `bank_name`        | Data          | Tên ngân hàng                               |
| `bank_ac_no`       | Data          | Số tài khoản                                |
| `...`              | ...           | _(xem mục Field mapping bên dưới)_         |
| `status`           | Select        | `Pending Review / Approved / Rejected / Synced` |
| `reject_reason`    | Small Text    | Lý do từ chối (HR nhập khi Reject)          |

### Field mapping với Employee

> **Claude Code**: Đọc file `/home/frappe/frappe-bench/apps/customize_erpnext/customize_erpnext/fixtures/custom_field.json` để hiểu cấu trúc custom field trên Employee. Tạo field tương ứng trên Employee Onboarding Form. Tên field trên Onboarding Form **KHÔNG cần prefix `custom_`**. Khi Sync, map ngược lại về đúng tên field trên Employee (thêm prefix `custom_` nếu cần).

Các field cần tạo tương ứng (đọc từ custom_field.json + Employee standard fields):
- `id_card_no`, `id_card_date_of_issue`, `id_card_place_of_issue`
- `id_card_cmnd_no`, `id_card_cmnd_date_of_issue`, `id_card_cmnd_place_of_issue`
- `marital_status`
- `bank_name`, `bank_branch`, `bank_ac_no`
- `education_level`, `university`, `major`
- Các field trong section **Current Address** trên Employee

### Quy tắc
- Mỗi Employee chỉ có **1 Employee Onboarding Form** (unique constraint trên field `employee`).
- Nhân viên mới Save form → status tự động = `Pending Review`.
- Nhân viên có thể quét QR lại để **sửa thông tin** nếu status vẫn là `Pending Review`.
- Khi HR chuyển `Approved` hoặc `Synced` → **không cho phép edit** nữa.
- Khi HR chuyển `Rejected` → nhân viên có thể sửa lại, status quay về `Pending Review` khi Save lại.

---

## Phần 1b: Single Doctype — `Employee Onboarding Settings`

### Mục đích
Cho phép HR cấu hình **bộ lọc nhân viên mới** hiển thị trên web page public. QR Code cố định, HR chỉ cần thay đổi settings khi có đợt nhận việc mới.

### Doctype config
- **is_single = True** — chỉ có 1 bản ghi duy nhất (dạng Settings page).

### Các field

| Field | Type | Ghi chú |
| --- | --- | --- |
| `filter_mode` | Select | `By Date Range / By Employee List` |
| **Section: By Date Range** | | |
| `from_date` | Date | Ngày joining bắt đầu |
| `to_date` | Date | Ngày joining kết thúc |
| **Section: By Employee List** | | |
| `employees` | Table (child) | Danh sách employee được chỉ định, child doctype chứa field `employee` (Link/Employee) |

### Cách hoạt động
- HR vào `Employee Onboarding Settings` → chọn `filter_mode`:
  - **By Date Range**: set `from_date` / `to_date` → web page chỉ hiển thị employee có `date_of_joining` trong khoảng này.
  - **By Employee List**: thêm employee vào child table → web page chỉ hiển thị những employee này.
- Web page (khi truy cập không có param `emp`) → gọi API → API đọc Settings → trả về danh sách tương ứng.
- HR cập nhật Settings bất kỳ lúc nào, không cần tạo lại QR.

---

## Phần 2: Public Web Page — Form nhập thông tin

### Yêu cầu kỹ thuật
- **Public page**, không yêu cầu login (Guest access).
- Mobile-friendly (nhân viên quét QR bằng điện thoại).
- Giao diện **đơn giản, dễ dùng** — tối thiểu UX phức tạp.

### URL params — 2 chế độ

| URL | Hành vi |
| --- | ------- |
| `/employee-onboarding` | **(QR cố định)** — Đọc bộ lọc từ `Employee Onboarding Settings`, hiển thị dropdown nhân viên theo cấu hình HR |
| `/employee-onboarding?emp=HR-EMP-00001` | Bỏ qua bước chọn, vào thẳng xác thực SĐT cho nhân viên đó |

### Luồng trên Web Page

**Bước 1 — Xác định nhân viên:**
- **Chế độ QR cố định** (không có param): Gọi API → API đọc `Employee Onboarding Settings` → trả về danh sách Employee theo bộ lọc HR đã cấu hình. Chỉ hiển thị Employee **chưa có Onboarding Form** hoặc có form ở status `Rejected` (cho phép sửa lại). Dropdown hiển thị: `"Nguyễn Văn A — 01/01/1990"` (tên + DOB để phân biệt trùng tên).
- **Chế độ `emp`**: Tự động xác định employee, bỏ qua dropdown, vào thẳng bước 2.
- Nếu employee đã có form ở status `Pending Review` → load dữ liệu đã nhập để nhân viên sửa tiếp.

**Bước 2 — Xác thực bằng SĐT:**
- Yêu cầu nhập 3 số cuối của số điện thoại đã cung cấp cho HR (Lưu trong cell_number của employee tương ứng).
- So khớp **3 số cuối** với `cell_number` trên Employee.
- Đúng → cho phép nhập form. Sai → từ chối, hiển thị thông báo lỗi.
<!-- - **Giới hạn 10 lần thử sai** mỗi employee (chống brute-force, reset sau 10 phút). -->

**Bước 3 — Nhập thông tin:**
- Hiển thị form với các field tương ứng Employee Onboarding Form.
- Phần **địa chỉ**: dùng cascading dropdown 2 cấp theo dịa chỉ mới sau sát nhập(Tỉnh →  Phường/Xã) + ô nhập số nhà/đường (xem Phần 3).
- Bấm **"Lưu thông tin"** → tạo/cập nhật Employee Onboarding Form, status = `Pending Review`.
- Hiển thị thông báo thành công, hướng dẫn nhân viên liên hệ HR nếu cần sửa sau khi đã Approved.

---

## Phần 3: API Địa chỉ hành chính Việt Nam (Reusable)

### Mục đích
API riêng biệt phục vụ tra cứu địa chỉ hành chính VN (trước & sau sáp nhập 07/2025). **Thiết kế tách biệt** để tái sử dụng cho các dự án khác trên cùng Frappe instance.

### Nguồn dữ liệu
- File JSON: `/home/frappe/frappe-bench/apps/customize_erpnext/customize_erpnext/api/address_converter/dia_chi_hanh_chinh_2025.json`
- API viết cùng thư mục.
- Cấu trúc: `Tỉnh/TP → Quận/Huyện (mảng "xa") → Phường/Xã (mảng "xa_cu")`.
- Có mapping cũ ↔ mới: các trường `quan_huyen_cu`, `tinh_cu`, `ghi_chu`.

### API Tra cứu

```
GET /api/method/customize_erpnext.api.address_converter.get_provinces
→ Trả về danh sách Tỉnh/TP [{ma, ten}]

GET /api/method/customize_erpnext.api.address_converter.get_districts?province_code=XX
→ Trả về danh sách Quận/Huyện thuộc tỉnh [{ma, ten}]

GET /api/method/customize_erpnext.api.address_converter.get_wards?district_code=XXXXX
→ Trả về danh sách Phường/Xã thuộc quận/huyện [{ma, ten}]
```

### API Chuyển đổi địa chỉ cũ ↔ mới

```
GET /api/method/customize_erpnext.api.address_converter.convert_address
    ?ward_code=00004&direction=old_to_new
→ Trả về phường/xã tương ứng sau chuyển đổi {old: {...}, new: {...}}

POST /api/method/customize_erpnext.api.address_converter.convert_batch
    Body: {codes: ["00004","00013"], direction: "old_to_new"}
→ Trả về danh sách mapping [{old: {...}, new: {...}}, ...]
```

### Yêu cầu
- Tất cả API phải **allow_guest=True** (dùng cho web page public).
- Hỗ trợ param `version=old|new` để lấy địa chỉ cũ hoặc mới.
- Response gọn nhẹ, chỉ trả `ma` + `ten` (tối ưu cho mobile).
- Có caching (dữ liệu địa chỉ ít thay đổi).
- Default tỉnh: **Quảng Ngãi** (xử lý ở frontend, không phải API).

---

## Phần 4: Trang HR — Quản lý & QR Code

### Trên Doctype Employee Onboarding Form (list view & form view)

**List view:**
- Filter theo `status`, `date_of_joining`.
- Hiển thị cột: employee_name, date_of_joining, status.

**Form view — các nút hành động:**

| Nút | Điều kiện hiển thị | Hành vi |
| --- | --- | --- |
| **Approve** | status = `Pending Review` | Chuyển status → `Approved` |
| **Reject** | status = `Pending Review` | Mở dialog nhập lý do → chuyển status → `Rejected` |
| **Sync to Employee** | status = `Approved` | Ghi dữ liệu sang Employee → chuyển status → `Synced` |

### QR Code

**QR cố định (chính):**
- URL cố định: `https://erp.tiqn.com.vn:8000/employee-onboarding`
- Danh sách nhân viên hiển thị được điều khiển bởi `Employee Onboarding Settings` (xem Phần 1b).
- HR in QR 1 lần, dán cố định tại phòng nhân sự hoặc gửi vào group chat. Trước mỗi đợt nhận việc chỉ cần cập nhật Settings.

---

## Phần 5: Permissions

| Role | Quyền |
| --- | --- |
| **HR Manager** | Full CRUD trên Employee Onboarding Form & Settings. Approve, Reject, Sync. |
| **HR User** | Read, Write trên Employee Onboarding Form & Settings. Approve, Reject, Sync. |
| **Guest (via API)** | Chỉ được gọi các whitelisted API: lấy danh sách employee, xác thực SĐT, lưu form, API địa chỉ. |
| **Employee** | Không cần quyền trên doctype này (mọi thao tác qua web page public). |

---

## Thứ tự triển khai đề xuất

1. **Đọc skill & reference** tại `/home/frappe/frappe-bench/.claude/skills` — tuân thủ pattern.
2. **Tạo API địa chỉ** — đọc JSON, viết API, test các endpoint.
3. **Tạo Doctype `Employee Onboarding Form`** và **`Employee Onboarding Settings`** — fields, permissions, các nút hành động.
4. **Tạo Public Web Page** — UI form, tích hợp API địa chỉ, xác thực SĐT.
5. **Tạo chức năng HR** — QR generator, Sync to Employee.
6. **Test end-to-end** trên mobile.

---

## Ghi chú kỹ thuật

- **Frappe API cho Guest**: dùng `@frappe.whitelist(allow_guest=True)` cho các API mà web page public cần gọi.
- **Mobile-first**: Web page phải responsive, test trên viewport 375px.
- **Không dùng Web Form built-in** của Frappe — dùng custom web page (HTML + JS + Frappe API) để có toàn quyền kiểm soát UX.
- **Doctype không dùng Submit** — `is_submittable = False`, quản lý trạng thái bằng field `status`.
- **Giao diện Web Form 100% tiếng việt, Doctype `Employee Onboarding Form` & `Employee Onboarding Settings` tiếng anh, translable**
- **Bỏ qua các dòng bị comment out trong promt này**
<!-- - **Rate limiting**: API xác thực SĐT giới hạn 10 lần sai mỗi employee, reset sau 10 phút. -->