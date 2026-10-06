# VN Address Search — Tỉnh/Xã dạng Autocomplete (tìm được)

> **Mục đích:** Cho 4 field địa chỉ Tỉnh/Xã trên Employee gõ để tìm (kể cả không dấu) thay cho Select chỉ cuộn chọn.
> **Phạm vi:** API nội bộ + helper JS
> **Trạng thái:** 🟢 Đang chạy (triển khai + commit 2026-10-06) · **Cập nhật:** 2026-10-06

Phương án đã chọn: **đổi fieldtype `Select` → `Autocomplete`**, giữ nguyên dữ liệu (lưu tên, không lưu mã).
Phương án DocType + Link đã cân nhắc và **không chọn** (`.claude/plans/vn_address_doctype.md`).

---

## 1. Hiện trạng (chưa đụng tới)

| Thành phần | File | Ghi chú |
|---|---|---|
| 4 field Select | `fixtures/custom_field.json` | `custom_{current,permanent}_address_{province,commune}`, options rỗng, bơm lúc chạy |
| Nạp options | `public/js/custom_scripts/employee.js` (`load_province_options`, `load_commune_options_for_type`) | gọi `api/vn_address/vn_address_api` |
| Trang self-update | `www/employee-self-update-info/` + `api/self_update_info/self_update_info_api.py` | render theo `widget` Address Province/Ward |
| Dữ liệu | bảng thô `provinces` (34) / `wards` (3.321) | nạp bởi `api/vn_address/import_vn_units.py` |

Dữ liệu đã cập nhật từ GitHub ngày 2026-10-06 (upstream `8b78ba5`), user quyết định **giữ**. Bản cũ còn
ở `bak20261006_provinces` / `bak20261006_wards` — xoá sau khi ổn định.

## 2. File trong thư mục này (MỚI, không file nào đang chạy import tới)

```
api/vn_address_search/
  __init__.py
  vn_address_search_api.py     ← API + hàm validate server
  test_vn_address_search.py    ← test READ-ONLY (20 assert)
  README.md                    ← file này
public/js/vn_address_autocomplete.js   ← helper JS, CHƯA có trong hooks.py
```

### API (`vn_address_search_api.py`)

| Method | Tham số | Trả về |
|---|---|---|
| `get_province_options()` | — | `[{value, label, code}]`, value = label = full_name |
| `get_ward_options(province)` | mã hoặc full_name tỉnh | `[{value, label, code}]` các xã của tỉnh |
| `check_address(province, ward)` | | `{valid, message}` |
| `get_address_error(province, ward)` | (Python) | chuỗi lỗi hoặc `None` |
| `validate_employee_address(doc, method)` | (Python) | throw nếu địa chỉ **vừa đổi** mà sai |

- `allow_guest=True` cho 3 method whitelisted, giống API cũ (trang self-update phục vụ NV không đăng nhập). Chỉ đọc.
- Sắp xếp theo **tên ngắn** (`Ba Tơ`), không theo full_name — để `Phường X` và `Xã X` không bị tách thành 2 khối.
- **Không cache**: 34 / tối đa 168 dòng, query < 1ms; không bao giờ trả dữ liệu cũ sau khi import lại.
- So khớp tên luôn `COLLATE utf8mb4_bin` (xem bẫy 4.1).

### Helper JS (`customize_erpnext.vn_address`)

| Hàm | Việc |
|---|---|
| `load_provinces()` / `load_wards(province)` | gọi API, nhớ kết quả trong trang |
| `set_options(frm, fieldname, options)` | thay `set_df_property('options')` — ghi `df.options` + `control.set_data()` |
| `enhance_control(control)` | filter bỏ dấu (`đ→d`) + `maxItems = 200`; idempotent |
| `enforce_choice(frm, fieldname)` | giá trị không có trong list → xoá + alert; trả `false` |
| `deburr(s)` | bỏ dấu, chữ thường |

## 3. Kết quả kiểm tra (2026-10-06)

```
bench --site erp.tiqn.local execute customize_erpnext.api.vn_address_search.test_vn_address_search.run
→ 20/20 passed
```
Gồm: 34 tỉnh / 3.321 xã; tra theo tên = theo mã; Ba Tơ ≠ Ba Tô, Sơn Hà ≠ Sơn Hạ; tỉnh 168 xã ≤ maxItems;
xã sai dấu / sai tỉnh / tỉnh trước sáp nhập bị từ chối; Employee không đổi địa chỉ → qua; hồ sơ tỉnh cũ
sửa field khác → qua. Test chỉ sửa doc trong bộ nhớ + `rollback`, không save.

## 4. Bẫy đã đo

### 4.1 Collation coi khác dấu là một
`utf8mb4_unicode_ci`: `Xã Ba Tơ`(21484) = `Xã Ba Tô`(21523), `Xã Sơn Hà` = `Xã Sơn Hạ` — cùng Quảng Ngãi,
8 cặp toàn quốc. ⇒ kiểm tra hợp lệ dùng `COLLATE utf8mb4_bin`; tìm kiếm cho người dùng bỏ dấu ở client.

### 4.2 Autocomplete của Frappe (`frappe/public/js/frappe/form/controls/autocomplete.js`)
- list chỉ đọc `df.options` lúc `make_input` → `set_df_property('options')` sau đó **không** làm mới (dòng 6-18).
- `FILTER_CONTAINS` phân biệt dấu (dòng 59-63) → gõ "ba to" không ra.
- `maxItems = df.max_items || 99` (dòng 45); tỉnh nhiều xã nhất 168.
- rời ô = lưu nguyên chữ đã gõ (dòng 115-124) → cần `enforce_choice` + validate server.

### 4.3 🔴 Trang self-update sẽ MẤT field im lặng
`self_update_info_api._ALLOWED_FIELDTYPES` không có `"Autocomplete"` → `_build_config` `continue` qua
4 field địa chỉ (8 dòng config, 912 phiếu). **Phải sửa cùng lúc với đổi fieldtype.**

### 4.4 Dữ liệu Employee không khớp danh sách
So khớp **phân biệt dấu** (đúng như validate sẽ dùng): **65** địa chỉ hiện tại không khớp, thường trú 0.
- ~50: tên trước sáp nhập (`Tỉnh Quảng Nam`, `TP Đà Nẵng`), nhập tay `Xã X, Tỉnh Y`, thiếu tiền tố.
- 15: chỉ khác hoa/thường hoặc vị trí dấu: `Hòa`/`Hoà`, `Thành Phố`/`Thành phố`, `xã`/`Xã`,
  `Đặc Khu`/`Đặc khu`, `Đăk Lăk`/`Đắk Lắk`, và lỗi gõ `Trà Bổng`/`Trà Bồng`.

Validate chỉ chạy khi địa chỉ **đổi** → 65 hồ sơ này vẫn mở/lưu được. Khi HR sửa địa chỉ của họ thì
buộc chọn lại từ list. Chuẩn hoá hàng loạt = việc riêng, cần user duyệt.

Tìm kiếm bỏ dấu khớp cả `Hòa` lẫn `Hoà` (cùng ra `hoa`) → người gõ kiểu cũ vẫn tìm được.

## 5. Triển khai

> 2026-10-06 đã làm A, B, C, E. Từ bước D chỉ thêm `"Autocomplete"` vào `_ALLOWED_FIELDTYPES` (user duyệt) — phần
> nâng cấp trang self-update (API mới + combobox) **để sau, khi user yêu cầu**.
> Khác plan: bước C đăng ký **hook validate riêng** trong `hooks.py` thay vì gọi từ `validate_employee_changes`
> (hàm đó return sớm với hồ sơ mới / NV chưa có chấm công).
> Bước A: `CustomField.save()` **từ chối** Select→Autocomplete (không có trong `ALLOWED_FIELDTYPE_CHANGE`) →
> sửa fixture JSON + `UPDATE tabCustom Field` trực tiếp (fixture import = delete + insert ignore_validate nên migrate
> sau ra đúng kết quả này).
> `copy_address` viết lại thành async: gán tỉnh → chờ list xã → gán xã (trước đây đổi tỉnh xoá luôn xã vừa copy).
> Kiểm tra sau deploy: `test_vn_address_search.verify_deploy`.
>
> **Nút copy địa chỉ (06/10/2026, user duyệt):** `custom_copy_permanent_address_to_other_adress` từ `Check` `is_virtual=1`
> → `Button`. Field ảo bị Frappe coi là read-only (`frappe/public/js/frappe/model/perm.js:222`) nên checkbox không bấm
> được từ commit `8f1beb5` (31/07/2026). Bỏ `read_only_depends_on` trên 3 field địa chỉ hiện tại. Địa chỉ hiện tại đã có
> và khác → `frappe.confirm` trước khi ghi đè. Cột tinyint cũ vẫn nằm trong `tabEmployee` (Frappe không drop) — vô hại.

### Bước A — Custom Field
- 4 field `fieldtype: Select → Autocomplete` (cột vẫn `varchar(140)`, không ALTER dữ liệu —
  `frappe/database/mariadb/database.py:196,208`).
- Sửa bằng `frappe.get_doc("Custom Field", "Employee-<fieldname>").save()` → `bench --site erp.tiqn.local
  export-fixtures --app customize_erpnext` → diff fixture chỉ đổi 4 dòng `fieldtype`.

### Bước B — `hooks.py` + `employee.js`
1. `doctype_js["Employee"]`: thêm `"public/js/vn_address_autocomplete.js"` **trước** `employee.js`.
2. `employee.js`:
   - `refresh`: `enhance_control` cho 4 field.
   - `load_province_options` / `load_commune_options_for_type`: dùng `load_provinces` / `load_wards`
     + `set_options`; bỏ `_province_code_map` (API nhận thẳng full_name).
   - nhánh xoá tỉnh trong `handle_province_change`: `set_options(frm, commune, [])`.
   - đầu 4 event change: `if (!customize_erpnext.vn_address.enforce_choice(frm, field)) return;`
   - giữ nguyên: default Quảng Ngãi, đổi tỉnh → xoá xã, address_full, dịch tiếng Anh, copy_address, before_save.
3. Sửa `hooks.py` ⇒ **restart** (hỏi trước).

### Bước C — Server
`api/employee/employee_validation.validate_employee_changes` gọi thêm
`vn_address_search_api.validate_employee_address(doc)`. Hook đã đăng ký sẵn → không sửa `hooks.py` cho bước này,
nhưng file .py đang được import ⇒ **restart**.

### Nơi đang dùng helper JS `public/js/vn_address_autocomplete.js`
- Form Employee (`doctype_js` Employee, đứng trước `employee.js`).
- Form Employee Self Update Info — ô tỉnh/xã HR sửa trên bảng `data_view` (`doctype_js` riêng).
  Kiểm tra cặp tỉnh/xã phía server dùng `get_address_error` (gọi từ `self_update_info_api.validate_desk_edit`).

### Bước D — Trang `/employee-self-update-info`
- `self_update_info_api._ALLOWED_FIELDTYPES` thêm `"Autocomplete"` (bẫy 4.3). Không cần sửa `index.html`.
- Tuỳ chọn (riêng): đổi API trang sang `vn_address_search` + combobox tìm kiếm.

### Bước E — Dịch + build
- `translations/vi.csv`: `Please select a value from the list`, `Please select a province before the ward`,
  `{0} is not a valid province`, `{0} does not belong to {1}`, `Invalid Address`.
- `bench build --app customize_erpnext` → clear-cache → restart (hỏi trước).

### Bước F — Dọn (sau khi ổn định)
- Xoá `bak20261006_provinces`, `bak20261006_wards`.
- Cân nhắc cho `api/vn_address/vn_address_api.py` dùng chung hàm của module này.

## 6. Test sau khi nối

| # | Thao tác | Kỳ vọng |
|---|---|---|
| 1 | Form NV mới | tỉnh mặc định Quảng Ngãi, ô xã có list |
| 2 | Gõ "ba to" (Quảng Ngãi) | ra `Xã Ba Tơ` và `Xã Ba Tô` |
| 3 | Gõ "dong" | ra cả xã có `Đông` |
| 4 | Gõ "hoa son" (Đắk Lắk) | ra `Xã Hoà Sơn` |
| 5 | Tỉnh 168 xã, ô trống | thấy đủ 168 |
| 6 | Gõ "abc", rời ô | ô bị xoá + alert |
| 7 | Đổi tỉnh | xã bị xoá, list theo tỉnh mới |
| 8 | address_full + địa chỉ tiếng Anh | cập nhật như trước |
| 9 | Data Import xã không thuộc tỉnh | dòng lỗi "does not belong to" |
| 10 | Mở + lưu NV tỉnh cũ (`TIQN-0887`) không sửa địa chỉ | lưu được |
| 11 | `/employee-self-update-info` | vẫn có 4 field địa chỉ, cascade chạy |
| 12 | Onboarding tạo NV | lưu được |

## 7. Rollback
4 field về `Select` + revert employee.js / hooks.py / employee_validation.py / self_update_info_api.py.
Không có dữ liệu nào bị đổi ⇒ không mất gì. Thư mục này có thể xoá nguyên khối.
