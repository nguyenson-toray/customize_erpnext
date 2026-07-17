# Employee Self Update Info — Tài liệu kỹ thuật

> Cập nhật: 26/06/2026

Trang web cho phép **nhân viên tự kiểm tra & cập nhật thông tin cá nhân** (không cần đăng nhập ERP). Điểm khác biệt cốt lõi so với trang `employee-self-update` cũ: **HR chọn động bất kỳ field nào của doctype `Employee`** (kể cả custom field thêm sau) để đưa lên form — không cần sửa code.

- Nhân viên **luôn thấy giá trị hiện có** của từng field để đối chiếu, chỉ sửa mục thay đổi.
- Dữ liệu submit **không ghi ngược vào Employee** — chỉ lưu lại để HR **export Excel** (so sánh cũ/mới).
- Trang cũ `employee-self-update` **không bị đụng tới** — đây là module song song, hoàn toàn mới.

---

## Cấu trúc file

```
www/employee-self-update-info/
  index.html        ← Frontend (HTML + vanilla JS)
  style.css         ← CSS (tách riêng) — serve static tại /employee-self-update-info/style.css
  index.py          ← get_context: no_cache + csrf_token

api/self_update_info/
  self_update_info_api.py   ← Public + HR APIs

api/vn_address/             ← DB địa chỉ VN (xem readme riêng trong thư mục này)
  import_vn_units.py
  vn_address_api.py

doctype/employee_self_update_info/            ← Lưu bản submit của từng NV
  employee_self_update_info.json/.py
  employee_self_update_info_list.js           ← List view: nút Download Excel
doctype/employee_self_update_info_setting/    ← Cấu hình (Single)
  employee_self_update_info_setting.json/.py/.js
doctype/employee_self_update_info_field/      ← Child table: field được chọn
  employee_self_update_info_field.json/.py
```

---

## Luồng trang

```
Step 1: Chọn nhân viên (combobox tìm kiếm theo mã hoặc tên)
   → get_eligible_employees()

Step 1b: Xác thực (CHỈ khi Setting bật "Validate by DOB")
   → verify_employee(employee_id, code)
   → Nhập 2 số cuối NGÀY SINH (DD), hoặc Bypass Code của admin

Step 2: Form động — render theo config + giá trị Employee hiện có
   → get_field_config() + get_form_data(employee_id, code)
   → Sửa field nào → ô tô vàng "đã đổi"
   → Địa chỉ: cascade Tỉnh → Phường/Xã (DB vn_address)

Step SUCCESS: Gửi xong
   → save_form_data(employee_id, data, code) → status = "Submitted"
```

**Vòng đời:** `Draft → Submitted`. Nhân viên có thể quay lại sửa & gửi lại bất cứ lúc nào (form luôn pre-load giá trị mới nhất: Employee hiện tại + đè bản đã lưu).

---

## Storage động — không còn schema cứng

Doctype `Employee Self Update Info` **không** có cột riêng cho từng thông tin. Toàn bộ giá trị lưu trong **`data_json`** dạng `{ "<employee_fieldname>": value, ... }` (key = đúng fieldname của Employee).

| Field | Kiểu | Ghi chú |
|---|---|---|
| `employee` | Link | autoname `field:employee` → tối đa 1 bản/NV |
| `employee_name` | Data | fetch từ Employee |
| `status` | Select | `Draft` / `Submitted` |
| `submitted_on` | Datetime | thời điểm gửi |
| `data_json` | Long Text | **toàn bộ dữ liệu form** (JSON) |

→ Thêm field mới = chỉ tick chọn trong Setting. **Không** sửa schema, **không** sửa code.

---

## Config field động (`Employee Self Update Info Setting`)

Singleton. HR cấu hình ở đây.

| Field | Kiểu | Mô tả |
|---|---|---|
| `filter_date` | Date | Lọc NV theo `date_of_joining` khi bấm "Add Employees" |
| `group` | Link → Group | Lọc NV theo `custom_group` |
| `department` | Link → Department | Lọc NV theo `department` |
| `custom_section` | Link → Section | Lọc NV theo `custom_section` |
| `employees` | Table | Danh sách NV được phép cập nhật |
| `validate_by_dob` | Check | Bật bước xác thực bằng ngày sinh |
| `bypass_code` | Int (0–99) | **Chỉ Administrator thấy**; mã vượt xác thực |
| `selected_fields` | Table | **Các field thực sự hiển thị trên form** (nguồn quyết định page) |
| `selected_fields_for_new_join` | Table | **Preset** field cơ bản cho nhân viên mới — KHÔNG ảnh hưởng page trực tiếp |

**Nút "Help"** (toolbar): mở dialog (extra-large) hướng dẫn toàn bộ cách dùng Setting này.

**Nút "+ Add Employee Field"** (`employee_self_update_info_setting.js`): mở dialog đọc `frappe.get_meta("Employee")`, liệt kê field hợp lệ (gồm custom field) → tick chọn. Custom field mới của Employee **tự xuất hiện** trong danh sách.

**Nút "+ Add Custom Field"**: thêm field **tự do, KHÔNG thuộc doctype Employee** (vd ghi chú, khảo sát…). Nhập: `key` (id lưu trữ), `label_vi`, `fieldtype` (Data/Date/Int/Select/Check/…), `options` (nếu Select), section, required. Giá trị chỉ lưu trong submission (`data_json`), **không đọc/ghi Employee**.

**New-Join Preset** (`selected_fields_for_new_join` + nút "↧ Fill Selected Fields from Preset"): bảng lưu sẵn **bộ field cơ bản cho nhân viên mới nhận việc**. Nhấn nút → **thay thế** toàn bộ `selected_fields` bằng nội dung preset (có hỏi xác nhận). Chỉ `selected_fields` quyết định field hiển thị trên page — preset chỉ là khuôn để điền nhanh.

**Nút "Add Employees" / "Clear All"**: thêm NV theo bộ lọc `filter_date` / `group` / `department` / `custom_section` (cần ít nhất 1 bộ lọc; nhiều bộ lọc = AND, chỉ NV `status=Active`). "Clear All" xoá danh sách + reset cả 4 bộ lọc.

**Mã QR + link** (field `info_html`): Setting hiển thị **QR code** + link tới `/employee-self-update-info` (URL tự theo host hiện tại) để gửi cho nhân viên. Lib `qrcode.min.js` load từ asset, fallback CDN `qrcodejs@1.0.0` (copy từ Setting cũ).

### Child `Employee Self Update Info Field`

| Cột | Mô tả |
|---|---|
| `employee_fieldname` | Tên field thật trong Employee — hoặc **key tự do** khi `is_custom` |
| `label_vi` | **Label tiếng Việt** — ưu tiên hiển thị. Trống → dùng label mặc định của field Employee |
| `detail` | Ghi chú giải thích thêm cho field — hiện **ngay dưới nhãn** trên trang NV (khối `.field-detail`, giữ xuống dòng `white-space:pre-line`; URL http/https tự thành **link bấm được** qua `linkify()` — luôn `esc()` trước) |
| `placeholder` | Chữ gợi ý mờ trong ô trống (VD "12 chữ số"). Áp cho input text/number/textarea; **bỏ qua** Date/Select/Check |
| `section_label` | Gom nhóm field cùng `section_label` vào 1 card |
| `widget` | `Auto` / `Address Province` / `Address Ward` |
| `required` | Bắt buộc nhập |
| `read_only` | Chỉ cho xem (không sửa, không submit) |
| `is_custom` | Field **không** thuộc Employee (chỉ lưu trong submission) |
| `custom_fieldtype` | Kiểu của custom field (khi `is_custom`) |
| `custom_options` | Options cho Select (mỗi dòng 1 giá trị) |

> **Field từ Employee** vs **Custom field:** field Employee thì `fieldtype/label/options` lấy từ meta Employee, có giá trị cũ để đối chiếu, import được. Custom field tự định nghĩa hoàn toàn trong row, **không có giá trị cũ** (cột "old" để trống trong Excel) và **không map vào Employee khi import**.

**Fieldtype hỗ trợ (v1):** Data, Date, Datetime, Time, Int, Float, Currency, Select, Check, Small Text, Text, Long Text, Link, Phone. (Attach / Table → giai đoạn sau.)

---

## Quy tắc Label (ưu tiên tiếng Việt)

Trong `get_field_config()`:

```python
label = row.label_vi or df.label or df.fieldname
```

1. `label_vi` (HR nhập) — **ưu tiên cao nhất**
2. `df.label` — label mặc định của field trong doctype Employee (KHÔNG dịch qua `_()`)
3. `df.fieldname` — phòng khi field không có label

> Lưu ý: site này nhiều field Employee đã được đặt label tiếng Việt sẵn (vd `date_of_birth` = "Ngày sinh"), nên fallback (2) thường đã ra tiếng Việt; field còn tiếng Anh (vd "Marital Status") thì HR điền `label_vi` để Việt hoá.

---

## Xác thực danh tính (`validate_by_dob`)

Khi bật, **bắt buộc** xác thực trước khi load & khi submit (chặn ở server, không bypass bằng gọi API trực tiếp; **áp cho MỌI người kể cả HR/Admin** — không có ngoại lệ theo role). Nút **"Gửi thông tin" bị ẩn** cho tới khi xác thực thành công (`.hidden{display:none !important}` để luôn thắng rule component, và `#submitbar` chỉ hiện trong `loadForm` sau verify).

- **Mã đúng** = 2 số cuối **NGÀY SINH** (DD, zero-pad). VD sinh `1989-07-04` → nhập `04` (gõ `4` cũng được — so sánh theo số).
- **Hoặc** = `bypass_code` của admin (HR dùng để vào bất kỳ NV; hoặc khi DOB lưu bị sai).
- **Tự động vào form** khi gõ đủ 2 số đúng (`oninput` gọi `doVerify()` — không cần bấm nút); sai → xoá ô, báo lỗi, gõ lại. Guard `_verifying` chống gọi trùng.

```python
_dob_day(emp)  = str(date_of_birth)[-2:]            # 'YYYY-MM-DD' → 'DD'
_num_eq(a, b)  = int(a) == int(b) (fallback string)  # bỏ qua số 0 đứng đầu
_code_ok       = _num_eq(code, bypass) or _num_eq(code, day)
_gate(...)     # throw nếu validate_by_dob bật và code sai
```

`bypass_code` giới hạn **0–99** (validate trong controller) để khớp ô nhập 2 chữ số, và **ẩn với mọi user không phải Administrator** (`employee_self_update_info_setting.js`), không bao giờ trả về cho trang web.

---

## Địa chỉ — cascade Tỉnh → Phường/Xã

Dùng DB `vn_address` (2 cấp sau sáp nhập 2025). Xem `api/vn_address/readme.md`.

- Field có `widget = Address Province` → select tỉnh (`get_provinces`).
- Field có `widget = Address Ward` → select phường/xã, **phụ thuộc tỉnh cùng section** (`get_wards(province_code)`).
- **Lưu vào Employee field là TÊN đầy đủ** (`full_name`, vd "Phường Ba Đình"), dùng `code` chỉ để cascade nội bộ (option `value=code`, `data-name=full_name`). Tương thích dữ liệu cũ vốn lưu tên.
- Pre-fill: match tên đã lưu với option theo `data-name`. Nếu tỉnh còn **trống** → tự điền mặc định **"Tỉnh Quảng Ngãi"** (`DEFAULT_PROVINCE`); không tô "đã đổi", nhưng sẽ được lưu khi submit.

---

## Header logo + tên công ty

- Logo: `/assets/customize_erpnext/images/logo_white.png` trên header (đổi file logo trong `public/images/` rồi `bench build` là được).
- Tên công ty: `index.py` lấy `default_company` (Global Defaults) → inject qua `window.COMPANY` (cùng cơ chế csrf, vì page bọc `{% raw %}`) → JS set vào `#company_name`.
- PDF dùng logo `logo_500.jpg` (nhúng base64 trong `_logo_data_uri`).

## Ô ghi chú thêm (remarks)

- Textarea cố định ở cuối form (luôn hiển thị), không bắt buộc.
- Lưu trong `data_json` dưới **key dành riêng `__remarks`** (hằng `REMARKS_KEY`), không phải field Employee → `save_form_data` xử lý riêng (không bị lọc theo config), `get_form_data` trả về `remarks`.
- Xuất hiện ở: cột cuối Excel ("Ghi chú (nhân viên)"), và trong PDF.

## Tải PDF sau khi submit

- Màn hình success có nút **"📄 Tải PDF thông tin đã gửi"** → gọi `download_submission_pdf` (POST, kèm `code` xác thực nếu bật) → nhận blob → tải về `ThongTin_<empid>.pdf`.
- PDF render server-side bằng `frappe.utils.pdf.get_pdf` (wkhtmltopdf) → tiếng Việt chuẩn, text chọn được. Gồm logo (base64) + tên công ty + mã/tên NV + thời điểm gửi + bảng (label tiếng Việt : giá trị đã gửi) + ghi chú.

## Quét QR CCCD (điền nhanh — tùy chọn)

Copy từ trang cũ, **rút gọn chỉ lấy 3 trường**: số CCCD, ngày cấp, số CMND cũ.
- QR mẫu :
 - 051089009620|212869262|Nguyễn Thái Sơn|04071989|Nam|Xóm 1, Thôn Phước Bình, Bình Nguyên, Bình Sơn, Quảng Ngãi|12082021
 - 051200012093|212588805|Nguyễn Thành Vinh|01062000|Nam|131/9/2 đường Hùng Vương, Tổ 5, Trần Hưng Đạo, TP. Quảng Ngãi, Quảng Ngãi|30052025||||
- **Chỉ hiện nút "📷 Quét mã QR trên CCCD"** khi field `custom_id_card_no` có trong `selected_fields` (gắn ngay trên ô nhập số CCCD).
- Quét chỉ là **tùy chọn điền nhanh & chính xác** — ô nhập tay vẫn luôn có, nhân viên có thể tự gõ.
- Thư viện `jsQR` load từ CDN (`jsqr@1.4.0`). Quét đa tỉ lệ (full → crop 60% → crop 35%, upscale 900px) + tăng tương phản (histogram stretch) để đọc QR nhỏ trên CCCD. Có nút bật đèn flash nếu thiết bị hỗ trợ.
- Format QR CCCD (pipe-separated): `parts[0]`=CCCD, `parts[1]`=CMND cũ, `parts[6]`=ngày cấp (ddmmyyyy → ISO).
- Điền vào (chỉ khi field tương ứng có trong config): `custom_id_card_no`, `custom_id_card_date_of_issue`, `custom_id_card_cmnd_no`, `date_of_birth` (ngày sinh, parts[3]) — và đánh dấu "đã đổi". CMND chỉ điền nếu đủ 9 số. Ngày cấp/ngày sinh trong QR là **ddmmyyyy** → `toISO` đổi sang `yyyy-mm-dd` (đã verify với CCCD thật; `<input type=date>` hiển thị theo locale trình duyệt nhưng giá trị lưu luôn đúng ISO).
- **Ngày hết hạn CCCD (`custom_id_card__date_of_expired`) tự tính** vì QR không chứa: `_cccdExpiryISO(dob, issueDate)` theo Luật Căn cước 2023 — mốc 14/25/40/60 tuổi, cấp trong 2 năm trước mốc → tính sang mốc kế; cấp ≥58 tuổi → không thời hạn (bỏ trống). VD: sinh 04/07/1989, cấp 12/08/2021 (32 tuổi) → hết hạn 04/07/2029 (40 tuổi).

> Khác trang cũ: **không** parse địa chỉ / không điền ngày sinh / không xử lý ảnh CCCD — đúng yêu cầu chỉ lấy CCCD + ngày cấp + CMND cũ.

**Fallback "Chụp / chọn ảnh CCCD" (cho QR nhỏ ~1.5cm trên CCCD cũ):** nút thứ 2 dùng `<input type="file" accept="image/*" capture="environment">` → mở camera app (tự lấy nét, ảnh độ phân giải cao). Ảnh tĩnh được decode bằng `_decodeImageForQR`: thử nhiều vùng cắt (full + center 60/40/25% + lưới 3×3 tile 40%) × upscale ~1200px × (ảnh gốc + tăng tương phản) → jsQR. Đáng tin hơn quét trực tiếp khi QR nhỏ/mờ; vẫn nhập tay được. (Đây là bước P5; các bước P1 BarcodeDetector / P2 zoom-focus / ZXing-wasm để dành nếu cần.)

---

## Lưu nháp cục bộ (chống mất dữ liệu khi reload)

Trang **không** giữ form state qua reload (đó là bản chất HTML, không liên quan `no_cache`) → dùng **localStorage**:

- **Tự lưu** (debounce 400ms) mỗi khi NV gõ/chọn — bắt qua delegate `input`/`change` trên `#form_area` nên phủ cả field render động & select địa chỉ.
- **Key theo từng NV**: `esui_draft_<employee_id>` → nhiều NV trên cùng máy không đè nhau.
- **Khôi phục** trong `loadForm`: nháp được **merge đè lên giá trị server TRƯỚC khi render** → cascade Tỉnh/Xã và mọi widget dựng đúng theo dữ liệu đang nhập dở; báo toast "Đã khôi phục thông tin bạn nhập dở trước đó".
- **Xoá nháp** sau khi gửi thành công (`clearDraft`); nháp **quá 1 ngày** (`DRAFT_TTL`) tự bỏ.
- Bọc try/catch: localStorage bị chặn (private mode) / đầy / JSON hỏng → bỏ qua, không chặn người dùng.

## Đánh dấu field đã thay đổi

- `get_form_data` trả về `original` (giá trị Employee gốc) và `values` (giá trị hiển thị = original đè bởi bản đã lưu).
- Frontend so sánh giá trị hiện tại với `original`; khác → thêm class `.changed` (ô tô vàng + badge "đã đổi").

---

## Combobox chọn nhân viên (1000+ NV)

Thay dropdown bằng ô tìm kiếm:
- Gõ **mã** (vd `TIQN-0148`) hoặc **tên** → lọc client-side.
- **Không phân biệt dấu** tiếng Việt (`deburr`: NFD + bỏ dấu tổ hợp + đ→d).
- Điều hướng phím `↑ ↓ Enter Esc`, hiển thị tối đa 50 kết quả/lần.
- `?emp=TIQN-xxx` trên URL → tự chọn sẵn.

---

## APIs

### Public (`allow_guest=True`)

| Method | Tham số | Trả về |
|---|---|---|
| `get_field_config()` | — | `{sections:[{label, fields:[...]}], require_dob}` |
| `get_eligible_employees()` | — | `[{employee_id, display_name, submitted}]` |
| `verify_employee(employee_id, code)` | mã xác thực | `{valid: bool}` (luôn `true` nếu tắt validate) |
| `get_form_data(employee_id, code=None)` | | `{original, values, has_existing, status, employee_name}` |
| `save_form_data(employee_id, data, code=None)` | `data` = JSON | `{status:"success", message}` |

> `get_form_data` & `save_form_data` đều gọi `_gate()` — nếu `validate_by_dob` bật mà `code` sai → throw.

### HR (cần đăng nhập: HR Manager / HR User / System Manager)

| Method | Mô tả |
|---|---|
| `download_excel(names=None)` | Export xlsx **2 sheet** (`New Data` / `Old Data`). `names`=JSON list hoặc null = tất cả |
| `download_submission_pdf(employee_id, code=None)` | (guest) PDF phiếu thông tin đã gửi — có logo + tên công ty + bảng field + ghi chú |

**Excel — thiết kế để import ngược vào Employee:**
- Cột: `[ID, Employee Name, <label từng field>...]`.
- **`ID`** = `Employee.name` → Data Import map vào record để **update** (chọn "Update Existing Records").
- Header field = **label gốc của field trong doctype Employee** (`df.label`, **KHÔNG** dùng `label_vi`) → khớp khi import. VD: "Date of Birth", "Mobile", "Bank Account No".
- **Không** có cột `Status` / `Submitted On` (tránh map nhầm vào field Employee).
- **Sheet 1 = `New Data`** (giá trị nhân viên nhập — sheet để import; ô khác giá trị cũ **tô vàng**).
- **Sheet 2 = `Old Data`** (giá trị Employee hiện tại — để đối chiếu).

> Frappe Data Import đọc **sheet đầu tiên** → `New Data` đặt đầu để import trực tiếp. Quy trình: Data Import (Employee) → Update Existing Records → upload file → map `ID` + các field → import.

---

## Review + Đồng bộ về Employee (ĐÃ TRIỂN KHAI)

**Vòng đời:** `Draft → Submitted → Reviewed → Synced`. **Phải Review trước, rồi mới Sync được.**

**Chỉ sync field thuộc Employee** (gồm `custom_`) — vì key trong `data_json` chính là fieldname Employee → `emp.set(fieldname, _coerce(value, fieldtype))`, **không cần `_SYNC_MAP`**.

| Loại field | Sync? |
|---|---|
| Field Employee thường / `custom_*` (Data/Date/Select/Int/Check/Link/Phone…) | ✅ ghi thẳng |
| Field địa chỉ `custom_*_province/_commune/_village` | ✅ ghi tên; **tự dựng lại `custom_*_address_full`** = village + commune + province |
| Custom field (`is_custom`) | ❌ không thuộc Employee |
| `__remarks` (ghi chú) | ❌ |
| `employee` / `name` (định danh) | ❌ bỏ qua |

**APIs (HR):**
- `review_forms(names)`: `Submitted → Reviewed` (bỏ qua record khác trạng thái). Ghi `reviewed_on/by`. Trả `{reviewed, skipped, results}`.
- `sync_to_employee(names)`: **chỉ record `Reviewed`**; mỗi record `emp.set()` các field thật → dựng lại `_full` → `emp.save()` trong **try/except + commit riêng từng record** (1 lỗi không chặn phần còn lại) → `Synced` + `synced_on/by`. Trả `{synced, failed, skipped, results:[{employee, ok, message}]}` — message chứa **lỗi Frappe trả về** nếu save Employee thất bại.
- `_coerce_for_employee(value, fieldtype)`: rỗng→None cho Date/Int/Float/Link; Check→0/1; Int/Float cast; còn lại string.

**Nút (desk, `__()` translatable):**
- **List view**: `Download Excel` (chọn → chỉ record đã chọn; không chọn → tất cả), `Mark Reviewed`, `Sync to Employee` (bulk theo record tick) → hiện **dialog kết quả** (bảng từng NV: ✅/❌ + chi tiết lỗi).
- **Form view**: `Mark Reviewed` (khi Submitted), `Sync to Employee` (khi Reviewed), `Edit in Portal` (khi chưa Synced).

**HR sửa dữ liệu** = nút **"Edit in Portal"** → mở `/employee-self-update-info?emp=<id>` (cùng trang NV, đầy đủ widget địa chỉ/QR/validation). HR **được mở BẤT KỲ nhân viên nào**, kể cả NV không có trong danh sách Setting (`_ensure_eligible` bỏ qua eligibility cho HR; nhân viên thường vẫn chỉ sửa được nếu có trong danh sách). Trang **vào thẳng** form NV (ẩn ô tìm/chọn khi có `?emp=`; load lỗi → hiện lại ô chọn).

> **Quan trọng — xác thực áp cho MỌI người:** khi `validate_by_dob` bật thì **kể cả HR/Admin cũng phải qua bước xác thực** (không còn HR-bypass). HR dùng **`bypass_code`** (mã 2 chữ số của admin) để vào bất kỳ NV mà không cần biết ngày sinh từng người. Sau khi HR sửa & gửi → status về `Submitted` (cần review lại).

**Hiển thị cho HR** (thay JSON thô khó đọc): form có field HTML `data_view` render bảng **Nhãn : Giá trị** theo section, ô khác giá trị Employee hiện tại **tô vàng + "Cũ: …"** (ẩn khi đã Synced). JSON thô nằm trong section **"Raw Data (JSON)"** thu gọn. API `get_submission_view(name)`.

> Lưu ý: sync **ghi đè** field Employee bằng giá trị NV khai; `emp.save()` có thể bung validate của Employee → lỗi được bắt & hiện chi tiết theo từng record, không làm hỏng các record khác.

---

## CSRF — www page

Trang `/www/` không có object `frappe` JS. Token inject qua Jinja: `window.csrf_token = "{{ csrf_token }}"`.
Mọi lời gọi API dùng `FormData` + field `csrf_token` (Frappe validate CSRF từ **form body**, không phải header). Xem hàm `api()` trong `index.html`.

---

## Ghi chú phát triển

**Thêm field cho nhân viên cập nhật:** chỉ vào Setting → "+ Add Employee Field" → tick → Save. **Hết.** (Không migrate, không sửa code — `get_field_config` đọc meta Employee trực tiếp.)

**Sau khi sửa code:**
- `index.html` (www): có hiệu lực ngay (no_cache).
- DocType / List / Setting JS: cần `bench build --app customize_erpnext`.
- Thêm/đổi **whitelisted method Python**: cần `bench restart` (gunicorn cache module — nếu không restart sẽ báo "Failed to get method for command").

**Site:** `erp.tiqn.local`.

**Bảo mật:** trang là `allow_guest` (giống trang cũ). `validate_by_dob` là lớp chống spam/đổi nhầm người. Khi cần siết chặt hơn, bật `validate_by_dob` + đặt `bypass_code`.
