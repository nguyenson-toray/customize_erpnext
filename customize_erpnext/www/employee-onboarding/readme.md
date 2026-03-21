# Employee Onboarding — Trang tự khai thông tin nhân viên mới

**URL:** `https://erp.tiqn.com.vn:8888/employee-onboarding`

Trang web cho phép nhân viên mới **tự điền thông tin cá nhân** mà không cần tài khoản ERPNext.
HR cấu hình danh sách nhân viên được phép điền tại **Employee Onboarding Settings**.

---

## Luồng hoạt động (4 bước)

```
Bước 1            Bước 2              Bước 3                  Bước 4
Chọn tên    →   Xác thực SĐT   →   Nhập thông tin   →   Xem lại & Lưu
```

### Bước 1 — Chọn tên

- Hệ thống tải danh sách nhân viên từ **Employee Onboarding Settings**.
- Chỉ hiển thị nhân viên chưa có form hoặc đã bị từ chối (Rejected).
- Nhân viên đã Approved / Synced **không xuất hiện** trong danh sách.
- Nếu truy cập qua link QR (`?emp=TIQN-XXXX`), bước này được bỏ qua, nhảy thẳng sang Bước 2.

### Bước 2 — Xác thực danh tính

Hệ thống dùng 2 số để xác minh, tùy theo dữ liệu Employee:

| Trường hợp | Yêu cầu nhập |
|---|---|
| Employee có `cell_number` | 2 số **cuối** số điện thoại |
| Employee không có `cell_number` | 2 số **ngày sinh** (DD, VD: ngày 05 → nhập `05`) |

> Mục đích: xác nhận đúng người, không cần mật khẩu.

### Bước 3 — Nhập thông tin

| Nhóm | Trường | Bắt buộc |
|---|---|---|
| **Thông tin cơ bản** | Ngày sinh, số điện thoại | Không (cập nhật từ Employee) |
| **CCCD** | Số CCCD (12 số), ngày cấp, nơi cấp | ✅ |
| **CCCD ảnh** | Ảnh mặt trước, mặt sau | Không (flag `upload_cccd`) |
| **CMND cũ** | Số CMND (9 số), ngày cấp, tỉnh cấp | Không |
| **Cá nhân** | Tình trạng hôn nhân | Không |
| **Ngân hàng** | Số tài khoản Vietcombank, chi nhánh | ✅ (trừ khi tick "Chưa có") |
| **Mã số thuế** | Mã số thuế cá nhân | Không (flag `tax_code`) |
| **Học vấn** | Trình độ, trường, chuyên ngành | Không |
| **Địa chỉ hiện tại** | Tỉnh/TP, Phường/Xã, Số nhà/Thôn | ✅ (flag `current_address`) |
| **Địa chỉ hộ khẩu** | Như trên, hoặc tick "Giống địa chỉ hiện tại" | ✅ (flag `permanent_address`) |
| **Địa chỉ nguyên quán** | Tỉnh/TP, Phường/Xã, Số nhà/Thôn | Không (flag `place_of_origin_address`) |
| **Email cá nhân** | Định dạng email | Không (flag `personal_email`) |
| **Liên hệ khẩn cấp** | Họ tên, số điện thoại (max 10 số) | ✅ khi flag bật (flag `emergency_contact`) |
| **Số con** | Số nguyên | Không (flag `number_of_childrens`, ẩn khi Độc thân) |
| **Size áo / giày** | Size áo, size giày/dép | Không (flag `shirt_size`, `shoe_size`) |

**Tính năng quét QR CCCD:**
- Nhấn nút **📷 Quét QR CCCD** để mở camera.
- Hệ thống tự động điền: Số CCCD, số CMND, ngày cấp, nơi cấp, địa chỉ hộ khẩu.
- Yêu cầu HTTPS (camera không hoạt động trên HTTP).

**Upload ảnh CCCD:**
- Mỗi mặt CCCD có 2 nút: **📷 Chụp** (mở camera trực tiếp) và **🖼 Thư viện** (chọn từ album).
- Sau khi chọn/chụp, giao diện crop hiện ra với **tỉ lệ cố định 85.6:54** (chuẩn kích thước CCCD).
- Ảnh được nén client-side: tối đa 1920×1211px, dung lượng ≤ 3MB (JPEG).
- Upload lên server, overwrite file cũ cùng tên (không tạo trùng).
- Đồng thời copy bất đồng bộ lên NAS Synology (xem mục Lưu trữ ảnh).

### Bước 4 — Xem lại & Lưu

- Hiển thị toàn bộ thông tin đã nhập để nhân viên kiểm tra.
- Nhấn **Xác nhận & Lưu** → tạo/cập nhật `Employee Onboarding Form` với status = `Pending Review`.
- Nhấn **Sửa lại** để quay về Bước 3.

---

## Feature Flags (Employee Onboarding Settings)

| Flag | Mô tả | Mặc định |
|---|---|---|
| `upload_cccd` | Hiện section upload ảnh CCCD | ✅ |
| `current_address` | Hiện địa chỉ hiện tại | ✅ |
| `permanent_address` | Hiện địa chỉ hộ khẩu | ✅ |
| `place_of_origin_address` | Hiện địa chỉ nguyên quán | ✅ |
| `personal_email` | Hiện email cá nhân | ✅ |
| `emergency_contact` | Hiện liên hệ khẩn cấp (bắt buộc khi hiện) | ✅ |
| `number_of_childrens` | Hiện số con (ẩn thêm khi Độc thân) | ✅ |
| `tax_code` | Hiện mã số thuế cá nhân | ✅ |
| `shirt_size` | Hiện size áo | ✅ |
| `shoe_size` | Hiện size giày/dép | ✅ |

---

## Đồng bộ sang Employee (`_SYNC_MAP`)

Khi HR bấm **Sync to Employee**, các trường sau được copy từ `Employee Onboarding Form` sang `Employee`:

| Form field | Employee field |
|---|---|
| `id_card_no` | `custom_id_card_no` |
| `id_card_date_of_issue` | `custom_id_card_date_of_issue` |
| `id_card_place_of_issue` | `custom_id_card_place_of_issue` |
| `id_card_cmnd_no` | `custom_id_card_cmnd_no` |
| `marital_status` | `marital_status` |
| `bank_name` | `bank_name` |
| `bank_ac_no` | `bank_ac_no` |
| `bank_branch` | `bank_branch` |
| `education_level` | `custom_education_level` |
| `university` | `custom_university` |
| `major` | `custom_major` |
| `current_address_*` | `custom_current_address_*` |
| `permanent_address_*` | `custom_permanent_address_*` |
| `place_of_origin_*` | `custom_place_of_origin_address_*` |
| `personal_email` | `personal_email` |
| `emergency_contact_name` | `person_to_be_contacted` |
| `emergency_phone_number` | `emergency_phone_number` |
| `number_of_childrens` | `custom_number_of_childrens` |
| `date_of_birth` | `date_of_birth` |
| `cell_number` | `cell_number` |
| `tax_code` | `custom_tax_code` |

> `shirt_size` và `shoe_size` **không đồng bộ** sang Employee — chỉ lưu trong Onboarding Form.

---

## Thuật toán quét QR CCCD

Sử dụng thư viện **jsQR** (client-side). Mỗi animation frame chạy 3 pass:

| Pass | Vùng scan | Upscale | Tần suất |
|---|---|---|---|
| 1 | Toàn frame | 1024px wide | Mỗi frame |
| 2 | 4 góc (60% frame, overlap ~35%) | 800px wide | Mỗi frame |
| 3 | Lưới 3×3 (40% frame, overlap ~25%) | 700px wide | Cách 1 frame |

- Canvas giữ **đúng tỉ lệ khung hình** (không bóp méo).
- `inversionAttempts: "attemptBoth"` — quét cả ảnh thường lẫn đảo màu.
- Camera yêu cầu: `facingMode: environment`, độ phân giải lý tưởng 1920×1080.

**Format QR trên CCCD Việt Nam:**
```
<cccd>|<cmnd>|<họ tên>|<DDMMYYYY ngày sinh>|<giới tính>|<địa chỉ>|<DDMMYYYY ngày cấp>
```
Hợp lệ khi: field[0] là 9–12 chữ số.

---

## Crop & nén ảnh CCCD (client-side)

Sử dụng **Cropper.js** với tỉ lệ cố định `85.6 / 54` (landscape, chuẩn ISO/IEC 7810 ID-1).

**Quy trình:**
1. Nhân viên chọn/chụp ảnh → modal crop hiện ra.
2. Người dùng chỉnh khung crop, nhấn **Lưu ảnh**.
3. Client resize xuống tối đa **1920 × 1211 px**.
4. Nén JPEG với chất lượng giảm dần `[0.88, 0.80, 0.72, 0.64, 0.55, 0.45]` cho đến khi ≤ 3MB.
5. Gửi base64 dataURL lên server.

Server kiểm tra giới hạn 4MB (buffer so với target client 3MB).

---

## Lưu trữ ảnh CCCD

### Trên server ERPNext

- Đường dẫn: `/sites/<site>/public/files/<mã NV> <họ tên> CCCD mặt trước.JPG`
- Ví dụ: `TIQN-1234 Nguyễn Văn A CCCD mặt trước.JPG`
- File cũ cùng tên bị **overwrite** khi nhân viên upload lại.
- URL trả về được URL-encode để hỗ trợ tên tiếng Việt.

### Copy lên NAS Synology (bất đồng bộ)

Ngay sau khi lưu file local, server enqueue một background job copy file lên NAS qua **SMB (smbprotocol)**.

- Thất bại không ảnh hưởng đến nhân viên — lỗi được log vào **Error Log** ERPNext.
- Credentials cấu hình trong `site_config.json`:

| Key | Mô tả |
|---|---|
| `nas_host` | IP hoặc hostname của NAS (vd: `10.0.1.5`) |
| `nas_share` | Tên share SMB (vd: `tiqn`) |
| `nas_domain` | AD domain (vd: `tiqn`) — được prepend vào username |
| `nas_user` | Tên tài khoản AD (vd: `hr`) |
| `nas_password` | Mật khẩu |

- **Thư mục đích** cấu hình tại field **Folder CCCD** trong **Employee Onboarding Settings**.
- Thư mục con được tạo tự động nếu chưa tồn tại (`_smb_makedirs`).

---

## Lưu trữ & Khôi phục form

- Khi nhân viên đã có form `Pending Review` hoặc `Rejected`, hệ thống **tải lại dữ liệu cũ** khi vào Bước 3.
- Banner thông báo trạng thái hiển thị ở đầu form.
- Nhân viên có thể chỉnh sửa và lưu lại (form cũ được **cập nhật**, không tạo mới).
- Form đã `Approved` hoặc `Synced`: **không thể chỉnh sửa**, nhân viên không xuất hiện trong danh sách chọn.

---

## Quy trình HR sau khi nhân viên nộp

```
Nhân viên lưu
     ↓
Employee Onboarding Form  →  status: Pending Review
     ↓
HR xem xét (ERPNext)
     ├─ Approve  →  status: Approved  →  Sync to Employee  →  status: Synced
     └─ Reject   →  status: Rejected  →  Nhân viên sửa & nộp lại
```

**Actions trong form ERPNext:**
- **Approve** — duyệt form (chỉ khi Pending Review).
- **Reject** — từ chối kèm lý do (chỉ khi Pending Review).
- **Sync to Employee** — đồng bộ dữ liệu sang doctype Employee (chỉ khi Approved).

**List View Actions:**
- **Approve Selected** — Duyệt các form đang chọn (chỉ Pending Review)
- **Download Excel** — Xuất Excel (chọn hoặc tất cả)
- **Download CCCD Photos** — Tải ZIP ảnh CCCD (chọn hoặc tất cả)
- **Generate QR Codes** — Tạo mã QR cho nhân viên (in hoặc chia sẻ)

---

## Cấu hình HR (Employee Onboarding Settings)

Đây là doctype **Single** (chỉ 1 bản ghi duy nhất).

| Chức năng | Mô tả |
|---|---|
| Chọn ngày → Thêm nhân viên | Tự động thêm tất cả nhân viên Active có `date_of_joining` = ngày chọn |
| Xóa tất cả | Xóa toàn bộ danh sách (nhân viên đã nộp form không bị ảnh hưởng) |
| QR Code | Hiển thị mã QR link trang onboarding để in/gửi cho nhân viên |
| Folder CCCD | Đường dẫn thư mục NAS lưu ảnh CCCD (có thể chỉnh sửa trực tiếp) |
| Feature Flags | 10 checkbox bật/tắt từng nhóm thông tin trên form |

---

## Các file liên quan

| File | Mô tả |
|---|---|
| `www/employee-onboarding/index.html` | Toàn bộ UI + logic client-side |
| `www/employee-onboarding/index.py` | Python context (CSRF token) |
| `api/onboarding/onboarding_api.py` | Tất cả API: get_eligible_employees, verify_phone, get/save form, upload ảnh, NAS copy, Excel/ZIP export |
| `doctype/employee_onboarding_form/` | DocType lưu dữ liệu nhân viên nộp |
| `doctype/employee_onboarding_settings/` | Cấu hình danh sách nhân viên + feature flags + folder NAS (Single) |
| `doctype/employee_onboarding_employee/` | Child table của Settings |
| `requirements.txt` | Python dependencies: qrcode, reportlab, Pillow, smbprotocol |

---

## Lưu ý kỹ thuật

- Trang **không dùng** `frappe` JS object (www page, không phải desk).
- CSRF token inject qua Jinja: `window.csrf_token = "{{ csrf_token }}"`.
- Mọi API call dùng `FormData` với `csrf_token` trong body (không dùng header).
- **Guest permissions**: Đọc feature flags qua raw SQL trên `tabSingles` vì Guest không có quyền Frappe ORM.
- Ảnh CCCD lưu URL-encoded (`%20`); `download_cccd_photos` phải `unquote()` trước khi resolve đường dẫn filesystem.
- `upload_cccd_photo` overwrite file cũ cùng tên — không tạo trùng.
- NAS copy chạy trong **background queue "short"** — không block response trả về cho nhân viên.
- SMB auth AD: domain prepend vào username (`domain\user`), không dùng kwarg `domain` riêng.
- **Frappe v16**: `get_all` cần `order_by` tường minh; `db.get_value` trả `int` cho Single DocType.
