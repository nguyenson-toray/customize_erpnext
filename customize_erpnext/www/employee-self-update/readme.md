# Employee Self Update — Tài liệu kỹ thuật

> Cập nhật: 26/03/2026

Hệ thống cho phép nhân viên tự cập nhật thông tin cá nhân qua web (không cần đăng nhập ERP). HR xem xét, duyệt, và đồng bộ vào doctype `Employee`.

---

## Thay đổi gần đây (26/03/2026)

| Tính năng | Chi tiết |
|---|---|
| **Bỏ qua xác thực** | Setting `verified_by_date_of_birth_or_phone_number` (Check, default=1). Nếu tắt → Step 2 bị bỏ qua, vào thẳng Step 3. API `get_page_settings()` trả về `{require_verification}`. |
| **Re-Open form** | HR có thể mở lại form Approved/Synced → Pending Review (giữ nguyên dữ liệu). API `reopen_form_bulk(names)`. Button ở List View và Form View. |
| **Sync education → child table** | `education_level`, `university`, `major` sync vào `tabEmployee Education` (`level`, `school_univ`, `maj_opt_subj`) thay vì custom fields. Trong `_SYNC_MAP` không có các field này; sync xử lý riêng trong `sync_to_employee`. |
| **Pre-fill từ Employee** | Nếu nhân viên chưa có form → `get_form_data` pre-fill đầy đủ từ Employee (reverse `_SYNC_MAP` + `tabEmployee Education` + `tabEmployee External Work History`). |
| **Group filter** | Setting có field `group` (Link → Group). Nếu đặt → `get_eligible_employees` chỉ trả về NV có `custom_group` tương ứng. |
| **Button Synced state** | Fix: Khi status=Synced, Re-Open được thêm trực tiếp (không qua Actions group) để tránh Frappe ẩn single-item dropdown. |
| **Ảnh giấy tờ khác trong review** | Step 4 (xem lại) hiện ảnh từ `other_docs_json` dưới dạng thumbnail grid. |
| **Sync to Employee (List + Form)** | Button "Sync to Employee" thêm vào cả List View và Form View. Sync custom fields qua `tabCustom Field` query (không phụ thuộc `frappe.get_meta().fields`). |
| **Approve button trên Form View** | Thêm Actions group với Approve (Pending Review), Sync + Re-Open (Approved). |
| **Fix duplicate marital_status** | Xóa option "Đã ly hôn" bị trùng trong `employee_self_update_config.json`. |

---

## Cấu trúc file

```
www/employee-self-update/
  index.html                          ← Toàn bộ frontend (single-file)

api/self_update/
  self_update_api.py                  ← Public + HR APIs

api/address_converter/
  api.py                              ← Tra cứu địa chỉ hành chính 2025
  dia_chi_hanh_chinh_2025.json        ← Dữ liệu địa chỉ (cache 24h)

doctype/employee_self_update_form/
  employee_self_update_form.json      ← Schema doctype lưu form
  employee_self_update_form.py
  employee_self_update_form.js        ← Form view: render ảnh other_docs, CCCD
  employee_self_update_form_list.js   ← List view: Approve/Excel/CCCD Photos

doctype/employee_self_update_setting/
  employee_self_update_setting.json   ← Schema doctype cấu hình
  employee_self_update_setting.py     ← Server methods: btn_add, btn_reset, ...
  employee_self_update_setting.js     ← Client: ẩn field_config_json với non-Admin
  employee_self_update_config.json    ← File config mặc định (source of truth)
```

---

## Luồng trang (4 bước)

```
Step 1: Chọn nhân viên
  → get_eligible_employees()
  → Dropdown danh sách NV (chưa Approved/Synced)
  → ?emp=TIQN-XXX trên URL → tự chọn + skip verify

Step 2: Xác thực danh tính
  → verify_identity(employee_id, code)
  → 2 số cuối SĐT (nếu có SĐT), hoặc 2 số ngày sinh (DD, zero-padded)

Step 3: Nhập thông tin
  → get_field_config() + get_form_data(employee_id)
  → Render từng section theo config
  → Upload ảnh CCCD → upload_cccd_photo()
  → Upload ảnh giấy tờ khác → upload_other_doc()
  → Quét QR CCCD → tự điền CCCD + địa chỉ

Step 4: Xem lại & xác nhận
  → validateForm() → hiện lỗi nếu thiếu bắt buộc
  → save_form_data() → status = "Pending Review"

Step SUCCESS: Màn hình hoàn tất
```

**Vòng đời trạng thái form:**
```
Pending Review → Approved → Synced
             ↘ Rejected        ↑
                    ↑          │ Re-Open (HR)
                    └──────────┘
```

- Nhân viên chỉnh sửa được khi: Pending Review hoặc Rejected.
- Không sửa được khi: Approved hoặc Synced.
- HR có thể Re-Open form Approved/Synced → Pending Review (giữ nguyên dữ liệu).

**Form View — Actions group:**

| Status | Buttons hiển thị |
|---|---|
| Pending Review | Actions → [Approve] |
| Approved | Actions → [Sync to Employee, Re-Open] |
| Synced | Re-Open (direct button, không qua group) |
| Rejected | *(không có button)* |

---

## Trạng thái toàn cục JS

```javascript
const S = {
  employee_id: null,          // ID nhân viên đang chọn
  employee_name: null,
  has_phone: true,            // Có SĐT để xác thực không
  config: null,               // Config sections từ get_field_config()
  formStatus: null,           // Pending Review / Approved / Rejected / Synced
  readOnly: false,            // true nếu đã Approved/Synced
  requireVerification: true,  // false → bỏ qua Step 2 (từ get_page_settings)
};

let provinces_cache = null;   // [{ma, ten}] — load 1 lần khi vào Step 3
let communes_cache = {};      // {province_ma: [{ma, ten}]} — lazy load
```

---

## Config form (`employee_self_update_config.json`)

**Vị trí:** `doctype/employee_self_update_setting/employee_self_update_config.json`

**Cơ chế hoạt động:**
- `get_field_config()` đọc từ `field_config_json` trong DB (tabSingles). Nếu trống → đọc file này làm fallback.
- Nhấn **↺ Reset to Default** trong Setting → ghi nội dung file vào DB.
- `bench migrate` **không** tự load file vào DB.
- Cache key: `employee_self_update_config` — bị xóa mỗi khi Setting được lưu (`on_update`).

**Workflow chuẩn khi thay đổi config:**
```
Sửa employee_self_update_config.json
  → Vào Employee Self Update Setting
  → Nhấn "↺ Reset to Default"
  → Config mới được áp dụng ngay
```

**Cấu trúc JSON:**

```json
{
  "version": "2.0",
  "sections": [
    {
      "id": "basic",
      "label": "Thông tin cơ bản",
      "ui_type": "standard",
      "fields": [
        {
          "form_field": "date_of_birth",
          "employee_field": "date_of_birth",
          "label": "Ngày sinh",
          "fieldtype": "Date",
          "required": true,
          "always_show": true,
          "row_id": "r1"
        }
      ]
    }
  ]
}
```

**Thuộc tính field:**

| Thuộc tính | Mô tả |
|---|---|
| `form_field` | ID của `<input>` trong HTML |
| `employee_field` | Field tương ứng trong Employee (null = không sync) |
| `fieldtype` | `Date`, `Data`, `Select`, `Int`, `Check`, `Attach`, `CmndProvince` |
| `required` | Bắt buộc (validate khi submit) |
| `row_id` | Cùng row_id → render trên cùng 1 hàng |
| `inputmode` | Thuộc tính HTML (`"numeric"` → chỉ nhận `[0-9]`) |
| `maxlength` | Thuộc tính HTML |
| `placeholder` | Thuộc tính HTML |
| `show_when` | `{field, value}` hoặc `{field, not_value}` — ẩn/hiện theo field khác |
| `allow_other_input` | Select có ô nhập tự do khi chọn "Khác" |
| `options` | Mảng string hoặc `[{value, label}]` cho Select |
| `required_unless_zero` | Bắt buộc trừ khi field khác = "0" (dùng cho bank_branch) |
| `auto_generated` | Field được tự tính (full address) — không render input |
| `hidden` | Render input nhưng ẩn đi |

**Các `ui_type` và render function:**

| ui_type | Render function | Mô tả |
|---|---|---|
| `standard` | `renderStandardSection` | Fields thông thường, hỗ trợ `row_id` |
| `address` | `renderAddressSection` | Cascade: Tỉnh → Xã + full address preview |
| `special_cccd` | `renderCCCDSection` | Số CCCD + ngày/nơi cấp + 2 ảnh + nút QR |
| `table` | `renderWorkHistorySection` | Bảng kinh nghiệm, có "no experience" checkbox |
| `bank` | `renderBankSection` | STK + chi nhánh (required trừ khi STK = "0") |
| `driving_license` | `renderStandardSection` | Check + Select hiện/ẩn theo checkbox |
| `other_docs` | `renderOtherDocsSection` | Upload nhiều ảnh giấy tờ |

---

## APIs — Public (`allow_guest=True`)

### `get_field_config()`
Trả về config JSON (DB hoặc fallback file).

### `get_eligible_employees()`
Danh sách NV trong Setting chưa Approved/Synced.
Nếu Setting có `group` → chỉ trả về NV có `custom_group` khớp.
Returns: `[{employee_id, display_name, birth_year, has_phone}]`

### `verify_identity(employee_id, code)`
- Có SĐT: `code` = 2 số cuối SĐT
- Không có SĐT: `code` = 2 số ngày sinh (DD, zero-padded, VD: ngày 5 → "05")

Returns: `{valid: bool, hint: string}`

### `get_page_settings()`
Trả về cài đặt trang. Hiện tại: `{require_verification: bool}`.
- `require_verification: false` → bỏ qua Step 2, vào thẳng Step 3.

### `get_form_data(employee_id)`
- Form tồn tại → trả về tất cả fields + `has_existing: true` + status + reject_reason
- **Chưa có form** → pre-fill đầy đủ từ Employee: tất cả fields trong `_SYNC_MAP` (reverse map) + `education_level/university/major` từ `tabEmployee Education` + `work_history_json` từ `tabEmployee External Work History`

### `save_form_data(employee_id, **kwargs)`
Tạo mới hoặc cập nhật form (block nếu đã Approved/Synced).
- Tự ghép `*_full` = village + commune + province
- Cập nhật `date_of_birth`, `cell_number` ngược vào Employee
- So sánh old vs new `other_docs_json` → xóa file không còn dùng
- Dùng `frappe.flags.ignore_permissions` khi load doc cũ (Guest không có quyền đọc)

Returns: `{status: "success", message: "..."}`

### `upload_cccd_photo(employee_id, side, image_data)`
- `side`: `"front"` hoặc `"back"`
- Lưu: `{id} {tên} CCCD mặt trước/sau.JPG` — overwrite nếu đã tồn tại
- Returns: `{file_url}`

### `upload_other_doc(employee_id, image_data)`
- Lưu: `{id} {tên} GiayToKhac {timestamp_ms}.JPG` — unique mỗi lần upload
- File cũ bị xóa bởi `save_form_data` khi submit (diff old/new `other_docs_json`)
- Returns: `{file_url}`

---

## APIs — HR (cần login, role HR Manager / HR User / System Manager)

| Method | Mô tả |
|---|---|
| `approve_form(form_name)` | Pending → Approved |
| `approve_form_bulk(names)` | Duyệt nhiều, skip không phải Pending. Returns: `{approved_count, skipped_count}` |
| `reject_form(form_name, reason)` | Pending → Rejected + lý do |
| `reopen_form_bulk(names)` | Approved/Synced → Pending Review, giữ nguyên dữ liệu. Returns: `{reopened_count, skipped_count}` |
| `sync_to_employee(form_name)` | Approved → Synced, ghi vào Employee theo `_SYNC_MAP` + education child table |
| `add_employees_to_setting(employee_ids)` | Thêm vào bảng employees của Setting |
| `get_employees_by_date(date)` | Lấy NV theo ngày vào làm (helper cho HR) |
| `download_excel(names=None)` | Export xlsx. `names=null` → tất cả |
| `download_cccd_photos(names=None)` | Export ZIP ảnh CCCD. Returns: `{filename, data: base64}` |

**`sync_to_employee` — logic đặc biệt:**
- Tất cả fields trong `_SYNC_MAP` → ghi vào Employee (query cả `tabCustom Field` để lấy đủ custom fields)
- `bank_name` luôn set = `"Vietcombank"`
- `work_history_json` (JSON string) → parse → ghi vào child table `external_work_history`
- `education_level` / `university` / `major` → ghi vào child table `education` (`level`, `school_univ`, `maj_opt_subj`)
- `other_docs_json`, `id_card_front_photo`, `id_card_back_photo` → **không sync**

---

## APIs — Address Converter (`allow_guest=True`)

Dữ liệu hành chính VN sau sáp nhập 7/2025. Cache Redis 24h.

| Method | Params | Returns |
|---|---|---|
| `get_provinces()` | — | `[{ma, ten}]` |
| `get_districts(province_code)` | `province_code` | `[{ma, ten}]` (đơn vị mới) |
| `get_wards(district_code)` | `district_code` | `[{ma, ten, ghi_chu}]` (phường/xã cũ) |
| `search_address_by_text(ward_name, district_name, province_name)` | Tên văn bản | `{old, new}` hoặc null |

**Thuật toán `search_address_by_text`:**
1. Normalize NFD (bỏ dấu), lowercase
2. Nếu `province_name` cho trước → chỉ tìm trong tỉnh đó
3. Với mỗi phường/xã cũ trong dữ liệu:
   - Ward match chính xác: score = 10; partial: score = 5
   - District match thêm: +5
4. Trả về kết quả score cao nhất

---

## Thuật toán QR CCCD

**Thư viện:** jsQR — load từ assets, fallback CDN jsdelivr.

**Vấn đề:** QR trên CCCD nhỏ và dày, thư viện chuẩn (html5-qrcode/ZXing) không decode được.

**Giải pháp — Multi-scale scan (3 crops/frame):**
```
1. Full frame (100%)
2. Center crop 60% → upscale 900px
3. Center crop 35% → upscale 900px
```

**Histogram equalization (contrast boost):**
```javascript
// Tìm min/max pixel → stretch tuyến tính về 0–255
// Áp dụng riêng cho từng crop trước khi feed vào jsQR
```

**Định dạng QR CCCD (pipe-separated):**
```
079123456789|Nguyễn Văn A|01011990|Nam|Xóm 1, Xã B, Huyện C, Tỉnh D|...|...
 [0]CCCD     [1]Tên        [2]DOB    [3] [4]Địa chỉ thường trú
```

**Sau khi quét:**
1. Điền `id_card_no`, `id_card_date_of_issue`
2. `id_card_place_of_issue` → "Cục Cảnh sát Quản lý hành chính về Trật tự Xã Hội"
3. Parse địa chỉ (split dấu phẩy, từ phải sang): `tỉnh ← huyện ← xã ← số nhà/thôn`
4. Gọi `search_address_by_text(xã, huyện, tỉnh)` → map sang đơn vị hành chính 2025
5. Điền province/commune/village cho **cả 3 địa chỉ**: `per` (hộ khẩu), `cur` (hiện tại), `ori` (nguyên quán)
6. Fallback nếu không tìm được xã: match tỉnh gần đúng (`_matchCCCDProvince`)
7. Gọi `_autoSetCmndProvince(provinceName)` → set tỉnh cấp CMND

---

## Thuật toán nén ảnh

```javascript
function _resizeAndCompress(srcCanvas, maxW, maxH, maxMB) {
  // Scale: fit trong maxW × maxH, không upsample
  // Thử quality: [0.88, 0.80, 0.72, 0.64, 0.55, 0.45]
  // Dừng khi blob.size ≤ maxMB * 1024 * 1024
}

function _compressDataUrl(dataUrl, maxW, maxH, maxMB) {
  // Wrap _resizeAndCompress: nhận dataUrl, trả về Promise<dataUrl>
}
```

| Loại ảnh | maxW | maxH | maxMB | Ghi chú |
|---|---|---|---|---|
| CCCD (sau crop Cropper.js) | 1920 | 1280 | 3 | Crop trước, compress sau |
| Giấy tờ khác | 1920 | 2560 | 2 | Compress trước khi upload |

---

## Validation màu border

```javascript
function _updateFieldColor(el) {
  const val = (el.value || "").trim();
  el.classList.remove("field-valid", "field-invalid");
  if (val) {
    el.classList.add("field-valid");        // xanh — có giá trị
  } else if (el.dataset.required === "1" && el.dataset.touched === "1") {
    el.classList.add("field-invalid");      // đỏ — bắt buộc + chưa điền + đã chạm
  }
  // mặc định xám — optional hoặc chưa chạm
}
```

- `data-required="1"` gán trong `_renderField` khi `field.required === true`
- `data-touched="1"` gán khi field bị `blur` hoặc khi nhấn Submit (gọi `_markRequiredTouched()`)
- `inputmode="numeric"` → thêm `oninput="this.value=this.value.replace(/[^0-9]/g,'')"` tự động

---

## Địa chỉ — Logic cascade

```
Province (Tỉnh/TP)  ← get_provinces()
    └── Commune (Xã/Phường) ← get_districts(province_code)
            └── Village (Số nhà/Thôn) ← nhập tay
                    └── Full address ← tự ghép
```

- Prefix: `cur` (hiện tại), `per` (hộ khẩu), `ori` (nguyên quán)
- Element IDs: `addr_{prefix}_province`, `addr_{prefix}_commune`, `addr_{prefix}_village`
- Checkbox "Giống địa chỉ hiện tại": ẩn/hiện fields đích, copy values khi check

---

## Doctype `Employee Self Update Form`

**Autoname:** `field:employee` → name = employee ID → tối đa 1 form/NV
**Permissions:** HR Manager (full), HR User (read/write/create) — **không có Guest**

**Các field và sync map:**

| Form field | Employee field | Ghi chú |
|---|---|---|
| `date_of_birth` | `date_of_birth` | Standard ERPNext |
| `cell_number` | `cell_number` | Standard ERPNext |
| `id_card_no` | `custom_id_card_no` | |
| `id_card_front_photo` | ❌ | Chỉ lưu trong form |
| `id_card_back_photo` | ❌ | Chỉ lưu trong form |
| `bank_ac_no` | `bank_ac_no` | |
| `bank_branch` | `custom_bank_branch` | |
| `social_insurance_number` | `custom_social_insurance_number` | max 12 số |
| `tax_code` | `custom_tax_code` | max 12 số (đồng bộ CCCD từ 2026) |
| `marital_status` | `marital_status` | Standard ERPNext |
| `emergency_contact_name` | `person_to_be_contacted` | |
| `relation` | `relation` | |
| `work_history_json` | `external_work_history` | JSON → child table |
| `other_docs_json` | ❌ | Không sync |
| `custom_vegetarian` | `custom_vegetarian` | Lưu dạng Data (không phải Select) |

---

## Doctype `Employee Self Update Setting`

**Loại:** Singleton (`issingle: 1`)
**Permissions:** HR Manager/System Manager (read/write), HR User (read only)
**Administrator** có thể xem/sửa `field_config_json` (logic ở `employee_self_update_setting.js`)

**Fields:**

| Field | Type | Mô tả |
|---|---|---|
| `filter_date` | Date | Ngày nhận việc — dùng để lọc khi thêm NV |
| `group` | Link → Group | Nếu đặt → `get_eligible_employees` chỉ trả về NV có `custom_group` tương ứng |
| `verified_by_date_of_birth_or_phone_number` | Check (default=1) | Nếu tắt → bỏ qua Step 2 xác thực |
| `field_config_json` | Long Text | Config JSON các section/field (override file mặc định) |
| `employees` | Table | Danh sách NV được phép cập nhật |

**Server methods (gọi từ nút trên form):**

```python
btn_add_by_date()   # Thêm NV theo filter_date và/hoặc group (cần ít nhất 1 trong 2)
btn_clear_all()     # Xóa toàn bộ bảng employees + reset filter_date và group về trống
btn_reset_config()  # Đọc employee_self_update_config.json → ghi vào field_config_json
```

**Logic bộ lọc khi thêm nhân viên:**

| `filter_date` | `group` | Kết quả |
|---|---|---|
| ✗ | ✗ | Báo lỗi — cần chọn ít nhất 1 |
| ✓ | ✗ | Lọc Employee theo `date_of_joining` |
| ✗ | ✓ | Lọc Employee theo `custom_group` |
| ✓ | ✓ | Lọc Employee theo cả 2 (AND) |

Bộ lọc này cũng được `get_eligible_employees()` dùng để lọc danh sách hiển thị trên web form (áp dụng trong số các NV đã có trong bảng employees).

**"Xóa tất cả"** xóa danh sách NV **và** reset `filter_date`, `group` về trống.

---

## List View actions

Tất cả button hiển thị trực tiếp trên toolbar (không gộp vào menu Action). Bị disable khi chưa chọn row.

| Button | Điều kiện | API |
|---|---|---|
| Approve Selected | Chọn ≥1 | `approve_form_bulk` — skip form không phải Pending |
| Download Excel | Chọn ≥1 | `download_excel` |
| Download CCCD Photos | Chọn ≥1 | `download_cccd_photos` (ZIP base64) |
| Re-Open | Chọn ≥1 | `reopen_form_bulk` — skip form không phải Approved/Synced |
| Sync to Employee | Chọn ≥1 | `sync_to_employee` — gọi tuần tự từng form, đếm done/failed |

**Excel bao gồm:** tất cả fields — kể cả `relation`, `custom_strengths`, `custom_favorite_sport`, `custom_vegetarian`.

---

## CSRF — www page

Trang `/www/` không có object `frappe` JS. Token inject qua Jinja:
```html
<script>window.csrf_token = "{{ csrf_token }}";</script>
```

**Pattern đúng** (Frappe validate CSRF từ form body, không phải header):
```javascript
async function api(method, args) {
  const fd = new FormData();
  fd.append("csrf_token", window.csrf_token);
  for (const [k, v] of Object.entries(args))
    fd.append(k, v == null ? "" : String(v));
  const res = await fetch(`/api/method/${method}`, {
    method: "POST", credentials: "same-origin", body: fd
  });
  if (res.status === 403) { location.reload(); throw new Error("Session expired"); }
  const data = await res.json();
  if (data.exc) throw new Error(/* parse _server_messages */);
  return data.message;
}
```

---

## Ghi chú phát triển

**Thêm field mới vào form:**
1. Thêm vào `employee_self_update_config.json` (trong đúng section)
2. Thêm vào `employee_self_update_form.json` (doctype schema)
3. Nếu cần sync → thêm vào `_SYNC_MAP` trong `self_update_api.py`
4. Thêm vào `download_excel` (columns + field_keys)
5. `bench migrate` → nhấn Reset trong Setting

**Ảnh CCCD vs other_docs:**
- CCCD: tên file cố định → overwrite khi upload lại. Giữ nguyên khi submit form.
- other_docs: tên file có timestamp → không overwrite. Xóa file cũ xảy ra trong `save_form_data`.

**Mã số thuế & BHXH:**
Lưu dạng `Data` (varchar), không phải `Int` — để bảo toàn số 0 đầu (VD: mã Hà Nội bắt đầu 001...).

**Địa chỉ hành chính:**
Dữ liệu sau sáp nhập 7/2025. Khi QR CCCD có địa chỉ cũ (trước sáp nhập), `search_address_by_text` tự map sang tên đơn vị mới. Commune dropdown hiển thị tên đơn vị hành chính mới (nhưng value lưu là tên, không phải mã).
