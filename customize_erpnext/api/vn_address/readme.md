# VN Address — Cơ sở dữ liệu địa giới hành chính Việt Nam

> Cập nhật: 26/06/2026

Module cung cấp dữ liệu **Tỉnh/Thành → Phường/Xã** (cấu trúc **2 cấp** sau sáp nhập 2025) cho cascade địa chỉ của trang `employee-self-update-info`. Dữ liệu được **import trực tiếp từ GitHub** (cập nhật theo từng nghị định của Chính phủ), lưu thành **bảng MySQL thường trong DB site** (không phải DocType).

**Nguồn:** https://github.com/thanglequoc/vietnamese-provinces-database (thư mục `mysql/`)

---

## Cấu trúc file

```
api/vn_address/
  import_vn_units.py   ← Tải SQL từ GitHub & nạp vào DB site (idempotent)
  vn_address_api.py    ← API tra cứu (get_provinces / get_wards / search_ward)
  readme.md            ← (file này)
```

> Module cũ `api/address_converter/` (đọc từ file JSON tĩnh) **vẫn giữ nguyên** cho trang `employee-self-update` cũ. `vn_address` là bản mới, độc lập.

---

## Các bảng được tạo trong DB site

| Bảng | Cột chính | Số dòng (v3.x) |
|---|---|---|
| `provinces` | `code` (PK), `name`, `full_name`, `name_en`, `administrative_unit_id` | 34 |
| `wards` | `code` (PK), `name`, `full_name`, `province_code` (FK), `administrative_unit_id` | 3.321 |
| `administrative_units` | `id` (PK), `full_name`, `short_name`, … | 5 |
| `administrative_regions` | `id` (PK), `name`, `name_en`, … | 8 |

- **2 cấp**: `wards.province_code` trỏ thẳng tới `provinces.code` — **không có cấp Huyện/Quận**.
- Tên bảng không trùng tiền tố `tab` của Frappe → không xung đột. `bench migrate` không quản lý các bảng này (đó là chủ ý — dữ liệu tham chiếu).

---

## Import / Cập nhật dữ liệu

Toàn bộ dữ liệu tải **trực tiếp từ GitHub** mỗi lần chạy → **không cần sửa code** khi tác giả cập nhật. Chỉ cần chạy lại lệnh:

```bash
bench --site erp.tiqn.local execute \
  customize_erpnext.api.vn_address.import_vn_units.import_vn_units
```

Lệnh `import_vn_units()` thực hiện (idempotent — chạy lại bao nhiêu lần cũng được):
1. Tải `mysql_CreateTables_vn_units.sql` + `mysql_ImportData_vn_units.sql` từ GitHub.
2. Gói lại thành 1 script: `SET FOREIGN_KEY_CHECKS=0` → `DROP TABLE` 4 bảng → CREATE → INSERT → `SET FOREIGN_KEY_CHECKS=1`.
3. Nạp qua client `mariadb`/`mysql` (pipe stdin — giữ nguyên multi-row INSERT & UTF-8), dùng credential từ `frappe.conf` (`MYSQL_PWD` để không lộ mật khẩu trên command line).
4. `frappe.clear_cache()` → API trả ngay dữ liệu mới.
5. In ra số liệu (vd `Imported VN address data: 34 provinces, 3321 wards`).

Quyền: chỉ **Administrator** hoặc **System Manager** (`@frappe.whitelist()`).

### Khi tác giả GitHub cập nhật (nghị định mới đổi tỉnh/xã)
→ **Chỉ chạy lại lệnh import ở trên.** Không cần sửa gì khác.

### Nếu tác giả ĐỔI CẤU TRÚC BẢNG (thêm/đổi cột, hoặc quay lại 3 cấp)
→ Cập nhật câu `SELECT` trong `vn_address_api.py` cho khớp tên cột mới. Kiểm tra nhanh cấu trúc hiện tại:

```bash
bench --site erp.tiqn.local mariadb -e "DESCRIBE provinces; DESCRIBE wards;"
```

---

## APIs (`vn_address_api.py`)

Tất cả `allow_guest=True` (trang self-update phục vụ nhân viên không đăng nhập), read-only, cache Redis 24h.

| Method | Tham số | Trả về |
|---|---|---|
| `get_provinces()` | — | `[{code, name}]` (name = `full_name`), sắp xếp theo tên |
| `get_wards(province_code)` | `province_code` | `[{code, name}]` các phường/xã của tỉnh |
| `search_ward(ward_name, province_name="")` | tên xã (± tên tỉnh) | `{province:{code,name}, ward:{code,name}}` hoặc `null` |

- `search_ward`: tra cứu gần đúng theo tên (LIKE) — phục vụ auto-fill QR CCCD trong tương lai; cascade cơ bản không cần.

**Nơi đang dùng (`get_provinces` / `get_wards`):**
- Trang `www/employee-self-update-info` (cascade Tỉnh → Phường/Xã).
- Form Employee desk: `public/js/custom_scripts/employee.js` (`load_province_options` / `load_commune_options_for_type`) — đã chuyển từ API cũ `address_converter` sang đây. Lưu ý: field Employee tên `custom_*_commune` nhưng API là `get_wards` (Commune ↔ Ward).
- Cache: `vn_address_provinces`, `vn_address_wards:<province_code>`. `import_vn_units` gọi `clear_cache` nên không cần xoá thủ công.

---

## HƯỚNG DẪN TEST API TỪ TRÌNH DUYỆT

Các endpoint là `allow_guest=True` → gõ thẳng URL vào thanh địa chỉ (GET, không cần CSRF):

```
# 34 tỉnh/thành
https://<site>/api/method/customize_erpnext.api.vn_address.vn_address_api.get_provinces

# phường/xã của 1 tỉnh (01 = Hà Nội, 79 = TP.HCM)
.../vn_address_api.get_wards?province_code=01

# tra cứu theo tên
.../vn_address_api.search_ward?ward_name=Ba Đình
.../vn_address_api.search_ward?ward_name=Long Xuyên&province_name=An Giang
```

Kết quả JSON bọc trong khoá `message`, vd:
```json
{"message":[{"code":"01","name":"Thành phố Hà Nội"}, ...]}
```

Test trong **JS Console (F12)** trên trang đã đăng nhập:
```javascript
frappe.call("customize_erpnext.api.vn_address.vn_address_api.get_wards",
            {province_code: "01"}).then(r => console.log(r.message));
```

Test bằng **curl** (guest, HTTPS cổng 8888):
```bash
curl -k "https://erp.tiqn.local:8888/api/method/customize_erpnext.api.vn_address.vn_address_api.get_provinces"
```

> Chi tiết tương tự cũng được ghi ở cuối file `vn_address_api.py`.

---

## Xử lý sự cố

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| `Address data not imported yet` | Chưa chạy `import_vn_units` → chạy lệnh import |
| `VN address import failed: ...` | Lỗi từ client mariadb (credential/charset) — đọc stderr in kèm |
| API trả dữ liệu cũ sau import | Cache — `import_vn_units` đã `clear_cache`; nếu vẫn cũ, `bench --site erp.tiqn.local clear-cache` |
| `Failed to get method for command` | Đổi method Python nhưng chưa `bench restart` (gunicorn cache) |
