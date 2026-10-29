# Employee Self Update Info — Tài liệu kỹ thuật

> **Mục đích:** trang www cho nhân viên tự kiểm tra / cập nhật thông tin cá nhân (không cần đăng nhập ERP),
> HR xem – sửa – in phiếu – Sync vào Employee.
> **Trạng thái:** đang chạy production · **Cập nhật:** 27/10/2026 (chuyển từ `www/` về đây — file không phải
> `.py` trong `www/` là trang công khai; Frappe còn cố dựng `.md` thành trang).

- HR **chọn động** field của Employee (kể cả custom field thêm sau) trong Setting — không sửa code.
- NV luôn thấy giá trị hiện có để đối chiếu, chỉ sửa mục thay đổi.
- Phiếu **không tự ghi vào Employee**: HR xem / sửa trên Desk rồi bấm **Sync**.

---

## File

```
api/self_update_info/              ← server (27/10/2026: tách từ 1 file 2.792 dòng, xem "Module" bên dưới)
  self_update_info_api.py          ← MẶT TIỀN: chỉ re-export; mọi đường dẫn whitelist giữ nguyên
  rules.py config.py values.py access.py receipt.py export.py portal.py desk.py sync.py
  test_self_update_sign.py         ← test Python (bench execute … run_all)
  README.md                        ← file này

www/employee-self-update-info/     ← trang NV (CÔNG KHAI — đừng để tài liệu / ghi chú ở đây)
  index.html                       ← markup + 2 biến Jinja (csrf_token, company)
  form.js                          ← toàn bộ JS trang. KHÔNG đặt tên index.js: Frappe đọc <basename>.js
                                     làm colocated_js mỗi request
  style.css
  index.py                         ← get_context: no_cache, csrf_token, company, asset_version (mtime
                                     form.js/style.css → ?v= tự đổi khi sửa file)
  open_with_browser.png            ← ảnh hướng dẫn "Mở bằng trình duyệt" (Zalo)

tests_js/self_update_info/         ← test jsdom của trang www (npm install && node run.js)

customize_erpnext/doctype/
  employee_self_update_info/           ← phiếu của từng NV (+ list view: Download File, Review, Sync)
  employee_self_update_info_setting/   ← Setting (Single)
  employee_self_update_info_field/     ← child: field hiển thị trên trang
  employee_self_update_info_document/  ← child: danh mục hồ sơ nộp kèm
  employee_self_update_employee/       ← child: NV được phép cập nhật

api/vn_address_search/             ← danh mục tỉnh/xã (README riêng)
api/employee/cccd_expiry.py        ← tính ngày hết hạn CCCD (dùng chung với form Employee)
```

## Module (server)

Phụ thuộc **1 chiều** theo thứ tự dưới (module dưới import module trên, không ngược lại).

| Module | Nội dung chính |
|---|---|
| `rules` | hằng số + luật dùng chung: `INFO_DT`, khoá `data_json` (`REMARKS_KEY`, `DOCUMENTS_KEY`), `_ALLOWED_FIELDTYPES`, `_LINK_AS_SELECT` (Gender → dropdown), `_FIELD_DEPENDS`, `_ALLOWED_TABLES`, `_TABLE_REQUIRED_IF`, câu cam kết mặc định |
| `config` | Setting → config field: `_build_config`, `_option_labels`, `_table_columns`, `_layout_width`, `_setting_documents`, `_info_for_sign_config`, `_address_pairs` |
| `values` | chuẩn hoá / kiểm tra / định dạng giá trị: `_normalize_text`, `_validate_value`, `_clean_table_value`, `_apply_depends`, `_apply_cccd_expiry`, `_portal_address_errors`, `_fill_from_employee`, hồ sơ nộp kèm (`_documents_snapshot`, `_document_status`), `_sign_join` / `_SIGN_GROUPS` |
| `access` | quyền vào trang: danh sách NV, mã ngày sinh / bypass, khoá sau khi gửi, token tải phiếu |
| `receipt` | phiếu PDF / PNG: `_build_submission_html` (ghép `_receipt_rows`, `_receipt_id_lines`, `_receipt_sign_block`, `_receipt_page`), `_hr_receipt_pdf` (luôn 1 trang), `_document_checklist_html`, `_html_to_png` |
| `export` | `download_excel`: All Info (Excel) + Info for Sign (Excel / PDF danh sách ký / PDF từng NV / PDF 1 trang mỗi NV gộp 1 file) |
| `portal` | API trang www (guest): `get_field_config`, `verify_employee`, `get_access_info`, `unlock_access`, `get_eligible_employees`, `get_form_data`, `save_form_data`, `download_submission_pdf` / `_image` |
| `desk` | form Desk: `get_submission_view`, `validate_desk_edit`, `apply_document_status`, `download_pdf_for_hr` |
| `sync` | `review_forms`, `get_syncable_fields`, `sync_to_employee` |

> 🔴 **Thay tạm (monkeypatch) 1 hàm trong test** phải gán vào MỌI module đang giữ tên đó — dùng `_set(name, value)`
> trong `test_self_update_sign.py`. Gán `api._build_config = fake` chỉ đổi ở mặt tiền, code trong module khác vẫn
> gọi bản thật → test "qua" mà không kiểm gì.

---

## Luồng trang www

```
1. Chọn NV (ô tìm theo mã / tên, bỏ dấu; ?emp=<id> chọn sẵn) ── get_eligible_employees
   └ đã gửi + Setting "Lock After Submit" → thẻ khoá: ngày sinh + mã mở khoá ── get_access_info / unlock_access
2. Xác thực (khi bật "Validate by DOB"): 2 số NGÀY sinh hoặc Bypass Code ── verify_employee
3. Form động: get_field_config + get_form_data (Employee hiện tại, đè bởi phiếu đã gửi + nháp cục bộ)
4. Hồ sơ nộp kèm (tick) → cam kết + ký → Gửi ── save_form_data → status "Submitted"
5. Tải phiếu PDF / PNG ── download_submission_pdf / _image (token ngắn hạn cho chính phiên vừa gửi)
```

**Vòng đời phiếu:** `Draft → Submitted → (Reviewed) → Synced`. NV gửi lại bao nhiêu lần cũng được (khi không bị khoá).

---

## Lưu trữ — `Employee Self Update Info`

1 phiếu / NV (`name` = mã NV). Giá trị khai nằm trong **`data_json`** `{ "<fieldname Employee hoặc key custom>": value }`
— thêm field = tick trong Setting, không đổi schema.

| Field | Ghi chú |
|---|---|
| `status` | Draft / Submitted / Reviewed / Synced |
| `submitted_on`, `reviewed_on/by`, `synced_on/by` | mốc thời gian |
| `date_of_birth`, `date_of_joining` | lấy từ Employee (lọc / in đầu phiếu HR) |
| `document_status`, `missing_documents` | **Tình trạng hồ sơ** (Documents Complete / Documents Missing + danh sách thiếu) — tính lại mỗi lần lưu |
| `commitment_confirmed`, `signed_on`, `signature` | chỉ trang www ghi được (`validate_desk_edit` chặn đường khác) |
| `device_info` | IP + model + platform (Client Hints), nối thêm mỗi lần gửi |
| `data_view` | HTML: bảng xem / sửa cho HR |
| `data_json` | toàn bộ dữ liệu |

Khoá đặc biệt trong `data_json`:
- `__documents` (`DOCUMENTS_KEY`): **bản chụp** danh mục hồ sơ lúc gửi `[{document, required, checked}]` — Setting đổi sau
  thì phiếu cũ vẫn đúng như lúc nộp. Sync không đọc.
- `__remarks`: ô "Ghi chú thêm" cũ (đã bỏ 16/10/2026); phiếu cũ còn thì vẫn hiện ở bảng HR / PDF / Excel.
- Bảng con (`education`, `external_work_history`): list dòng, dòng đã Sync mang `name` của dòng Employee.

---

## Setting — `Employee Self Update Info Setting`

**Tab General** (dùng hằng ngày)

| Field | Mô tả |
|---|---|
| `filter_date`, `department`, `custom_section`, `group` + nút **Add Employees** / **Clear All** | thêm NV Active theo bộ lọc (AND); không lọc gì → hỏi rồi thêm toàn bộ NV Active. Bảng `employees` có nút **Paste Codes** (dán danh sách mã NV); tự bỏ dòng trùng |
| `info_html` | QR + link `/employee-self-update-info` để gửi NV |
| `validate_by_dob`, `bypass_code` (0–99, chỉ Administrator thấy) | xác thực bằng 2 số ngày sinh |
| `allow_browser_local_storage` | cho lưu nháp cục bộ |
| `force_open_devices_browser` | trong Zalo → bắt mở bằng trình duyệt thiết bị |
| `allow_receipt_download` | NV được tải phiếu PDF / ảnh sau khi gửi (mặc định bật). Tắt → màn hình "Đã gửi" không có nút tải, server chặn cả lượt tải có token (`_gate_receipt`); HR đăng nhập vẫn tải được |
| `save_file_type` | PDF / PNG cho phiếu NV tải (ẩn khi tắt tải phiếu) |
| `lock_after_submit`, `bypass_code_for_unlock` | khoá sau khi gửi + mã mở khoá (không bao giờ gửi xuống trang) |
| `disable_review` | bỏ bước Reviewed, Sync thẳng từ Submitted |
| `commitment_text` | câu cam kết (giữ xuống dòng, trống → câu mặc định) |
| `start_notes` | **Start Screen Notes** (Text Editor): ghi chú ở màn hình đầu, trên thẻ "Chọn nhân viên" (cần chuẩn bị gì, thông tin dùng vào việc gì…). `get_field_config` gửi `start_notes_html` đã qua `sanitize_html` (bỏ script / on* / javascript:), trang chèn thẳng, link mở tab mới; editor trống → ẩn; ẩn ở màn hình "Đã gửi". Có ghi chú → nút **"Bắt đầu"** ngay dưới, bấm mới hiện thẻ "Chọn nhân viên" và ẩn ghi chú (đã đọc) (thẻ này mặc định ẩn trong HTML, JS cho hiện — không nháy); trống / lỗi tải config → hiện ô chọn NV ngay; link `?emp=` bỏ qua bước này. Thay cho ghi chú mục đích viết cứng ở đầu form (đã bỏ 28/10/2026). **Ảnh** dán vào editor là file private gắn vào Setting → Guest mở `/private/files` bị 403: `_guest_note_images` đổi src thành `start_note_image?fid=…&v=<content_hash>` (guest, GET; chỉ trả file ảnh gắn Setting VÀ đang có trong ghi chú, không SVG; cache 1 ngày). src tuyệt đối `https://host/private/files/…` (editor có khi lưu kiểu này) cũng được đổi. Ảnh cạnh dài > 1200px → thu nhỏ + JPEG q85 (`_note_image_content`, cache Redis 7 ngày theo content_hash; 2,1 MB → ~190 KB); GIF / ảnh lỗi → trả nguyên. CSS: ảnh co theo khung, cao tối đa 70vh, giữ tỉ lệ |
| `start_button_delay` | **Start Button Delay** (giây, mặc định 20; 0 = không chờ): lần đầu mở trên 1 máy, nút "Bắt đầu" khoá + đếm ngược "Vui lòng đọc hướng dẫn trên… (N giây)" (tính theo đồng hồ). Bấm Bắt đầu → `localStorage.esui_start_notes_seen` = dấu băm của `start_notes_html` → lần sau mở ngay; HR sửa ghi chú → chờ lại 1 lần; localStorage bị chặn → lần nào cũng chờ |

**Tab Form Setup** (thường cố định)

| Field | Mô tả |
|---|---|
| `document_checklist` | danh mục **hồ sơ nộp kèm**: `document` + `required`. NV tick hồ sơ đã có; thiếu hồ sơ Required vẫn gửi được, chỉ thành "Documents Missing". Trống → không hiện |
| `selected_fields` | **field thực sự hiện trên trang** (nút "+ Add Employee Field" / "+ Add Custom Field") |
| `selected_fields_for_new_join` | **preset** cho đợt NV mới; nút "↧ Fill Selected Fields from Preset" thay toàn bộ `selected_fields` |

### Cột của mỗi dòng field (`Employee Self Update Info Field`)

| Cột | Mô tả |
|---|---|
| `employee_fieldname` | fieldname Employee — hoặc key tự do khi `is_custom` |
| `label_vi` | nhãn hiển thị (trống → label của Employee) |
| `section_label` | gom field vào 1 thẻ (thứ tự thẻ = thứ tự xuất hiện); tiền tố số "1. " bị bỏ khi in phiếu |
| `detail`, `placeholder` | hướng dẫn (giữ xuống dòng, URL tự thành link) / chữ mờ trong ô |
| `widget` | Auto / Address Province / Address Ward / **Select + Other** (field Data của Employee: dropdown theo `custom_options` + "Khác" mở ô gõ tự do; field không phải Data → coi như Auto) — vd ăn chay |
| `layout_width` | **Width on Form**: Full / Half — 2 field Half liền nhau cùng 1 hàng (xem "Bố cục") |
| `required`, `read_only`, `enable` | |
| `auto_fill_data` | 1: điền sẵn từ Employee / lần gửi trước; 0: luôn để trống. Phiếu PDF: field Auto Fill chưa khai → lấy Employee |
| `info_for_sign` | field in trong **Info for Sign** và **phiếu PDF phía HR** |
| `validation`, `min_length`, `max_length`, `regex` | Digits / Phone / Email / CCCD / CMND / Past / Future / Regex / Capitalize Each Word / Sentence Case |
| `is_custom`, `custom_fieldtype`, `custom_options` | `custom_options` cũng là danh sách của widget Select + Other. Field không thuộc Employee (chỉ lưu trong phiếu, không Sync) — vd câu hỏi "Bạn có trả phí cho công ty Toray/ Công ty tư vấn…" (Select Có / Không) |
| `table_columns`, `max_rows` | bảng con: cột hiển thị (`fieldname \| nhãn \| bắt buộc`, trống → mặc định), số dòng tối đa (trống = 3; Học vấn / Kinh nghiệm đang = 1) |
| `option_labels` | Select: nhãn hiện trên trang `giá trị \| nhãn` (vd size dép) — phiếu in vẫn dùng bản gọn |

Fieldtype hỗ trợ: Data, Date, Datetime, Time, Int, Float, Currency, Select, Check, Small Text, Text, Long Text,
Link (Gender → dropdown Nam/Nữ), Phone, Autocomplete (tỉnh/xã), Table (chỉ `education`, `external_work_history`).

---

## Trang www — chi tiết

### Bố cục (Width on Form, 27/10/2026)
- Mỗi thẻ là lưới 2 cột (`.fgrid`): Full = cả hàng, Half = nửa hàng — **cả trên điện thoại**; < 360px mới về 1 cột.
- Cặp **cố định** theo thứ tự Setting: trong 1 Section, Half liền nhau ghép 1-2, 3-4… Half lẻ, hoặc bạn cặp đang ẩn
  (field "chỉ hiện khi…"), → class `solo` = cả hàng; cặp không đổi chỗ khi ẩn/hiện (`layoutHalfRows`).
- Nhãn 2 ô trong cặp cao bằng nhau (đo lại khi xoay màn hình / web font tải xong) → 2 ô nhập thẳng hàng. Detail của
  field Half nằm **dưới** ô nhập. Bảng con luôn Full.
- Đang dùng: Giới tính | Ngày sinh · Dân tộc | Tôn giáo · SĐT | Email · Ngày cấp | Ngày hết hạn · Mối quan hệ | SĐT
  khẩn cấp · Size áo | Size dép · GPLX | Tình trạng GPLX · Số TK | Chi nhánh. **Tỉnh / Xã để Full** (Half bị cắt chữ
  trên điện thoại); Số CCCD Full (có nút quét QR + hướng dẫn).

### Field "chỉ hiện khi…" (`_FIELD_DEPENDS`)
`custom_driving_license_status` chỉ hiện (và khi hiện thì bắt buộc) khi GPLX = "Chưa"; ẩn → xoá trắng. Cùng luật ở
trang, `save_form_data`, `validate_desk_edit`.

### Bảng con (Học vấn, Kinh nghiệm làm việc)
- Mỗi dòng 1 thẻ; "+ Thêm" tới `max_rows` (đủ thì hiện "Tối đa N.", trừ `max_rows = 1` — chỉ 1 thẻ, dòng này thừa); bảng trống → sẵn 1 thẻ trống. Điền sẵn **`max_rows` dòng mới nhất** của Employee.
- Học vấn: từ Trung cấp trở lên bắt buộc Trường + Ngành (Năm TN không); THCS / THPT ẩn và xoá trắng Trường / Ngành / Năm.
- Dòng có `name` của Employee → Sync sửa đúng dòng đó.

### Hồ sơ nộp kèm
Thẻ ngay trên cam kết: mỗi hồ sơ 1 ô tick, `*` = bắt buộc. Gửi kèm `documents` (JSON tên hồ sơ đã tick); server dựng bản
chụp `__documents`. Lần mở sau tick sẵn theo lần gửi trước (nháp cục bộ thắng).

### Địa chỉ (Tỉnh → Xã)
Ô gõ để tìm (bỏ dấu, ↑ ↓ Enter Esc, ✕ xoá), **chỉ nhận giá trị trong danh mục** `api/vn_address_search`; xã khoá tới khi
có tỉnh, đổi tỉnh → xoá xã. Lưu **tên đầy đủ**. Tỉnh trống → mặc định "Tỉnh Quảng Ngãi" (trừ field `auto_fill = 0`).
Server `_portal_address_errors`: chỉ kiểm cặp KHÁC giá trị Employee hiện tại (hồ sơ tên cũ không đổi vẫn gửi được).

### CCCD
- 2 cách: **📷 Quét mã QR** (trực tiếp) hoặc nhập tay. Nút **🖼️ Chụp / chọn ảnh CCCD** đang TẠM ẨN (comment trong
  `renderField` → `scanUi`, 28/10/2026); code đọc ảnh giữ nguyên để bật lại. Điền số CCCD,
  ngày cấp, CMND cũ, ngày sinh (`_parseVnCCCDQR` → `_fillFromCCCD`).
- **Bộ giải mã (28/10/2026, thay jsQR từ CDN):** `BarcodeDetector` gốc nếu trình duyệt có (Chrome Android → ML Kit);
  không có — trình duyệt trong Zalo (phần lớn NV), Safari — → ZXing-C++ WASM qua `barcode-detector` 3.2.2 +
  `zxing_reader` 3.1.3, **tự lưu** ở `public/js/lib/zxing/` (kèm giấy phép; `prepareZXingModule.locateFile` ép đường dẫn
  `.wasm`, mặc định thư viện tải từ jsDelivr). Chỉ tải khi mở máy quét; lần đầu ~1,1MB. Tải lỗi → báo nhập tay.
- **Giải mã trong Web Worker** (`www/employee-self-update-info/qr_worker.js`, 28/10/2026): luồng chính chỉ cắt khung
  ngắm bằng `createImageBitmap` rồi chuyển sang worker → hình camera không giật (đo CPU /4: 32 → 60 khung hình/s, luồng
  chính hết bị khoá). Thiếu Worker / createImageBitmap / OffscreenCanvas hoặc worker lỗi → giải mã trên luồng chính như
  cũ. URL worker kèm `?v=` của form.js; `index.py` tính `asset_version` cả qr_worker.js. `?qrdebug=1` hiện `wasm·worker`.
- Camera: zoom ~2x + lấy nét liên tục **nếu có** (`_qrSetupTrack`; webview iPhone thường không có) → nhắc cầm cách
  15–20cm (không zoom: 10–15cm). Giải mã ~10 lần / giây vùng khung ngắm (vuông 60% cạnh ngắn) ở độ phân giải gốc, cứ
  4 lần thử cả khung.
- Ảnh chụp (khi bật lại nút): cả ảnh rồi 11 vùng cắt, cùng bộ giải mã.
- Chẩn đoán trên máy thật: `?qrdebug=1` (engine / độ phân giải / zoom / lấy nét / đèn / lần/s); `?qrengine=wasm` ép ZXing.
- Số liệu đo jsQR vs ZXing: `tests_js/self_update_info/qr_bench/README.md`.
- **Ngày hết hạn luôn tự tính** theo Luật Căn cước 2023 (mốc 14/25/40/60 tuổi; cấp ≥ 58 tuổi → không thời hạn), không cho
  nhập; server tính lại khi gửi (`_apply_cccd_expiry`) và khi lưu Employee (`api/employee/cccd_expiry`).

### Chuẩn hoá chữ (không hỏi)
Field chữ widget Auto (trừ Email): NFC, gộp khoảng trắng, chèn dấu cách chữ–số (`Xóm1` → `Xóm 1`), viết hoa đầu ô;
Capitalize Each Word / Sentence Case theo `validation`. Trang (`normalizeText`, khi rời ô + khi gửi) và server
(`_normalize_text`, nguồn chuẩn) cùng luật. Giá trị mặc định khi trống: Dân tộc = "Kinh".

### Lưu nháp cục bộ (Setting `allow_browser_local_storage`)
`localStorage` key `esui_draft_<mã NV>` (gồm cả hồ sơ đã tick), debounce 400ms, quá 1 ngày bỏ, xoá sau khi gửi; nháp đè giá
trị server trước khi render.

### Cam kết + chữ ký
Câu cam kết lấy từ Setting (`config.commitment_html`, server đã escape, xuống dòng = `<br>`). NV bắt buộc tick + ký
(canvas → PNG data URL ≤ 400 KB); HR mở `?emp=` thì không bắt buộc (không ký → giữ chữ ký cũ). **Đã ký thì phải tick**,
kể cả HR (trang + `save_form_data`; bug 28/10/2026: HR ký mà chưa tick vẫn gửi được).

### Select + Other
Config gửi `fieldtype: "Select"`, `options: ["", …custom_options]`, `allow_other: true`, `widget: "Auto"`. Trang thêm
`<option value="__other__">Khác</option>` + ô `f_<fieldname>__other` (hiện khi chọn Khác); giá trị gửi = chữ trong ô (chuẩn hoá
như Data). Giá trị đã lưu không có trong danh sách → mở form chọn sẵn Khác + điền ô. Chọn Khác mà ô trống → báo thiếu (kể cả
field không bắt buộc). Server: bỏ kiểm "giá trị ∈ options", chữ ngoài danh sách chuẩn hoá như Data; Desk editor = ô chữ.

### Zalo
Webview Zalo chặn tải file. `force_open_devices_browser` bật → overlay hướng dẫn "Mở bằng trình duyệt" (`?zalo=1` để thử
ngoài Zalo); tắt → nút lưu hiện phiếu dạng ảnh PNG để chụp màn hình.

### CSRF
Trang www không có object `frappe`: `window.csrf_token = {{ csrf_token | tojson }}` trong `index.html`, mọi lời gọi gửi
`FormData` kèm field `csrf_token` (hàm `api()` trong `form.js`).

---

## Xác thực + khoá

- `validate_by_dob`: mã đúng = 2 số ngày sinh (so theo số, `4` = `04`) hoặc `bypass_code`; áp cho MỌI người kể cả HR.
  Gõ đủ 2 số là tự vào form.
- `lock_after_submit`: đã gửi (`submitted_on`) → vào lại cần **cả** 2 số ngày sinh **và** `bypass_code_for_unlock`.
  Khoá cũng chặn tải phiếu; ngoại lệ: **download token** HMAC (`encryption_key`, mã NV, cửa sổ 15 phút → hiệu lực ~15–30 phút) trả về từ
  `save_form_data` cho chính phiên vừa gửi.
- HR đăng nhập mở `/employee-self-update-info?emp=<mã>` được với **mọi** NV (kể cả không có trong danh sách Setting).
- Chặn ở server (`_gate_edit`, `_gate_receipt`); `get_access_info` / `unlock_access` chỉ phục vụ giao diện.

---

## Phiếu PDF / PNG

| | Phiếu NV tải (trang www) | Phiếu HR (Generate PDF, PDF Split, PDF 1 trang / NV) |
|---|---|---|
| Field | mọi field trong config | chỉ field tick **Info for Sign** |
| Đầu phiếu | Mã NV, Họ tên | bảng 6 cột: Mã NV · Họ tên · Giới tính / Ngày sinh · SĐT · Ngày nhận việc |
| Gộp dòng | không | địa chỉ 1 dòng "thôn, xã, tỉnh"; CCCD + ngày cấp; liên hệ khẩn cấp; GPLX; size áo / dép (`_SIGN_GROUPS`) |
| Hồ sơ nộp kèm | 2 dòng "Đã có" + "Tình trạng hồ sơ" | bảng: ☑ hồ sơ NV đã tick, `*` bắt buộc, ô Đạt / Không đạt / Quá hạn / Khác để HR đánh tay, dòng Tình trạng hồ sơ |
| Chưa ký | không in cam kết | in cam kết + ô trống ký tay |
| Lề | 15mm | 10mm |
| Số trang | tự nhiên | **luôn 1 trang**: `_hr_receipt_pdf` thu nhỏ (wkhtmltopdf `--zoom`) 1.0 → 0.99 → … → 0.95 → … 0.7 tới khi vừa |

- PNG: cùng HTML, `wkhtmltoimage` + Pillow (nền trắng, optimize).
- Ngày in dd/mm/yyyy; Select in nhãn tiếng Việt (`_sign_value_vi`).
- Zoom 1.0 thường tràn 2 trang nhưng 0.99 đã vừa (wkhtmltopdf dàn trang khác khi zoom ≠ 1) → ~0,8 giây / phiếu.

---

## Desk (HR)

**Form phiếu**
- `data_view`: bảng Nhãn : Giá trị theo Section, ô khác Employee tô vàng + "Cũ: …". Sửa trực tiếp (text, select, date,
  tỉnh / xã, bảng con) → Save. Chốt chặn `validate_desk_edit`: chỉ HR, chỉ field có editor, giá trị hợp lệ; phiếu
  **Synced** khoá — trừ tick **hồ sơ nộp kèm** (vẫn tick được khi NV nộp bổ sung).
- Mục **Documents**: tick hồ sơ → Save → Tình trạng hồ sơ tính lại.
- Nút: **Generate PDF**, **Mark Reviewed** (khi `disable_review = 0`), **Sync to Employee** (dialog chọn field, mặc định
  tick field đã đổi).

**List view**
- Lọc theo **Document Status**.
- **Download File**: `All Info` (Excel 2 sheet New Data / Old Data, cột ID để Data Import update Employee) hoặc
  `Info for Sign` với 4 định dạng:
  - *PDF Split For Each Employee*: mỗi NV 1 PDF (nhiều NV → ZIP);
  - *PDF 1 Page Per Employee (1 File)*: cùng phiếu đó, gộp 1 file, mỗi NV 1 trang theo mã NV;
  - *PDF Combine To 1 File*: danh sách ký A4 ngang (STT | NV | Thông tin | Nội dung | Ghi chú | Chữ ký), cỡ chữ lớn nhất
    vừa trang (dò nhị phân), tick nhiều mục thì lùi bố cục 4/5 → 3/4 → 2/3 NV mỗi trang;
  - *Excel*.
  PDF tối đa 100 phiếu / lần.
- **Mark Reviewed**, **Sync to Employee** cho nhiều phiếu.

---

## Sync vào Employee (`sync_to_employee`)

- Chỉ field Employee thật (kể cả `custom_*`); field custom, `__remarks`, `__documents`, `employee` / `name` bỏ qua.
- Trạng thái nhận: Submitted + Reviewed khi `disable_review` bật, ngược lại chỉ Reviewed.
- Địa chỉ: dựng lại `custom_*_address_full` = thôn, xã, tỉnh.
- Bảng con: dòng có `name` → sửa đúng dòng; dòng không `name` mà giống hệt 1 dòng Employee → coi là dòng đó (Sync lại
  không nhân bản); còn lại → thêm. Dòng Employee ngoài phiếu: giữ trong giới hạn **Max Rows** (giữ dòng mới nhất), phần dư
  **bị xoá**. Sau `emp.save()` ghi `name` dòng Employee ngược vào phiếu.
- Mỗi phiếu lưu + commit riêng (1 phiếu lỗi không chặn phiếu khác); kết quả báo số field, dòng giữ / xoá.

---

## Test

```bash
# Python (không ghi DB, rollback): 348 phép kiểm
bench --site erp.tiqn.local execute customize_erpnext.api.self_update_info.test_self_update_sign.run_all

# Trang www (jsdom, JS thật của form.js): 176 phép kiểm
cd apps/customize_erpnext/customize_erpnext/tests_js/self_update_info && npm install && node run.js
# thử bản nháp trước khi ghi đè trang đang chạy:
ESUI_PAGE_DIR=/đường/dẫn/bản-nháp node run.js
```

---

## Khi sửa code

| Sửa | Cần |
|---|---|
| `form.js`, `style.css`, `index.html` | có hiệu lực ngay (trang đang chạy production — sửa trên bản nháp + test trước) |
| `.py` trong `api/self_update_info/` | **`bench restart`** (worker giữ module cũ; thêm hàm mới mà chưa restart → lỗi im lặng) |
| JSON DocType | `bench --site … execute frappe.reload_doc --args '["customize_erpnext","doctype","<tên>"]'` (bump `modified`) |
| JS Desk (form / list / Setting) | `bench --site … clear-cache` + tải lại trang |
| Chuỗi giao diện | tiếng Anh trong code, dịch ở `locale/vi.po` (`#. source: tiqn`) rồi `bench compile-po-to-mo --app customize_erpnext` |

**Thêm field cho NV cập nhật:** Setting → tab Form Setup → "+ Add Employee Field" → tick → Save. Không sửa code.
