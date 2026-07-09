# Packing List — Module Documentation

Chức năng **độc lập** (không link DocType ERPNext có sẵn) để lập **Packing List** xuất hàng
thành phẩm. Mỗi mặt hàng phân rã theo **màu × size**; hệ thống tự xếp thùng carton, tính
khối lượng/CBM/số container, cho **chụp ảnh mỗi thùng** và **đọc số cân (OCR)**.

Module: `Customize Erpnext`. Code: `customize_erpnext/customize_erpnext/doctype/packing_list/`.

---

## 1. DocTypes

### Packing List (master, `autoname: format:{no}`)
- **Header:** `no` (ID = No, tự đổi tên khi sửa No — xem §9), `date`, `contract_no`, `style`,
  `destination`, `customer` (Data, không link), `description_of_goods`.
- **Carton config:** `carton_types` (child *Packing List Carton Type*), `container_type`
  (20GP/40GP/42GP/40HC/45HC), `combine_mode`, `small_carton_threshold`,
  `max_size_per_mixed_carton` (2/3/4), `weight_mode` (Net to Gross / Gross to Net).
- **Input:** `items_text` (Code), `weight_text` (Code).
- **Totals (read-only):** `total_quantity`, `total_carton`, `total_containers`,
  `total_net_weight`, `total_gross_weight`, `total_cbm`.
- **HTML ảo:** `total_carton_detail` (thùng nguyên/mix), `size_color_summary` (bảng qty size×màu).
- **Child:** `details` → *Packing List Detail*.

### Packing List Detail (child, 1 dòng = 1 thùng)
`carton_no`, `color`, `size`, `contents`, `pcs`, `net_weight` (read-only),
`gross_weight` (sửa tay được — từ cân), `empty_weight` (tare của thùng, read-only),
`cbm`, `carton_type` (nhãn `L*W*H`), `sku`, `upc` (Small Text — đa dòng), `photo` (Attach Image).

### Packing List Carton Type (child)
`length`, `width`, `height` (cm), `max_items` (sức chứa/thùng), `empty_weight` (tare kg),
`cbm` (read-only, tự tính). Dòng **đầu tiên** = loại thùng lớn/mặc định (theo thể tích).

---

## 2. Nhập liệu (copy-paste từ Excel, cột cách nhau bằng Tab)

**1. Items** (`items_text`) — mỗi dòng = 1 (màu + size):
```
Color   Size   Quantity   SKU            UPC
Boundary Black   SM   39   200333-116-SM   196926047493
```
- SKU/UPC tùy chọn. Dòng header tự bỏ qua. Trùng (màu,size) → cộng dồn.
- Thứ tự size/màu = theo lần xuất hiện đầu tiên.

**2. Net Weight per Piece** (`weight_text`) — khối lượng 1 cái theo size:
```
Size   Weight
SM   0.4
```
- Thiếu size đang dùng → **Generate báo lỗi** (tránh Net = 0 âm thầm).

Parser: `_parse_items()` → `(qty_map, sizes, colors, sku_map)`; `_parse_weight()` → `{size: kg}`.

---

## 3. Thuật toán xếp thùng (`build_cartons`)

1. **Thùng nguyên (đầy):** mỗi (màu,size,qty) → `qty // cap` thùng đầy `cap` cái
   (`cap` = max_items của thùng lớn). Phần dư `qty % cap` → hàng lẻ.
2. **Ghép hàng lẻ** theo `combine_mode` (`_combine_leftovers`):
   - **No Combine:** mỗi phần lẻ 1 thùng riêng.
   - **By Color:** ghép các size cùng màu.
   - **By Size:** ghép các màu cùng size.
   - **By Color & Size:** ghép tất cả.
   - Dùng **First-Fit-Decreasing** — **không bao giờ xé lẻ 1 (màu,size) ra 2 thùng**.
   - Mỗi thùng ghép chứa **tối đa `max_size_per_mixed_carton`** size khác nhau.
3. **Chọn loại thùng** (`_pick_box`, khi có ≥2 loại): thùng **đầy → thùng lớn**;
   thùng **chưa đầy → thùng nhỏ** nếu tổng pcs ≤ `small_carton_threshold`
   (0 = mọi thùng chưa đầy dùng thùng nhỏ), và ≤ sức chứa thùng nhỏ.
4. **Sắp xếp:** thùng nguyên (theo màu→size) trước → thùng ghép sau, gom theo loại thùng.
   Đánh số `carton_no` tuần tự.
5. Mỗi thùng: `net = Σ(pcs_size × weight_size)`, `gross = net + empty` (tare),
   `cbm = L×W×H/1.000.000`. `total_containers = ceil(total_cbm / dung_tích_container)`
   (20GP≈28, 40GP≈58, 42GP≈58, 40HC≈68, 45HC≈86 — hằng số trong code).

---

## 4. Bảng chi tiết & hiển thị

- **Thùng nguyên:** 1 màu + 1 size; `contents` **để trống**; `sku`/`upc` là giá trị đơn.
- **Thùng ghép:** `color`/`size` liệt kê các giá trị cách nhau `, `;
  `contents`/`sku`/`upc` **đa dòng** (mỗi item 1 dòng, `\n`), Contents dạng `Color-Size: qty Pcs`.
  (Small Text → in ra `<br>`; CSV export dùng `:` không dùng `×`.)
- `validate` (`_recalc_totals`): cộng lại tổng; xóa Contents ở dòng không phải mix;
  nếu `weight_mode = Gross to Net` → `net = gross − empty` (xem §6).
- **Size/Color Summary** (`get_size_color_summary_html` + JS): bảng pivot qty size×màu, có Total.
- **Total Carton Detail** (JS): số thùng nguyên vs thùng ghép.

---

## 5. Edit Mix (chỉnh tay thùng ghép)

Dialog ma trận (thùng ghép × mảnh lẻ). `apply_mix_edit`:
- Giữ thùng nguyên (dựng lại từ color/size/pcs); pool = pieces trong các thùng mix hiện tại.
- Bắt buộc **bảo toàn** (tổng pieces đã xếp = pool) và mỗi thùng ≤ sức chứa loại thùng.

---

## 6. Khối lượng: Net ↔ Gross (`weight_mode`)

- **Net to Gross (mặc định):** Net từ số cái; Gross = Net + tare.
- **Gross to Net:** nhập **Gross** (từ cân) → **Net = Gross − tare** (`empty_weight`).
  Tính live khi gõ Gross trong lưới, và khi lưu (`_recalc_totals`).

---

## 7. Ảnh thùng + OCR số cân

**Chụp (JS):** nút *📷 Take Photo* → tích 1 dòng thùng → camera (getUserMedia; fallback
camera thiết bị trên HTTP) → crop khung thùng → resize ≤1600px, JPEG 0.88.

**Lưu (`save_carton_photo`):** File tại `/private/files/packing_list/`, tên
`{No}_{CartonNo}_{Color}_{Size}.jpg`. Chụp lại cùng thùng → **xóa ảnh cũ + kg cũ**.
Sau khi lưu: **clear checkbox + tự tích thùng kế tiếp** (`select_next_carton`).

**OCR (`read_scale_ocr`, ssocr):** ngay sau lưu, dialog tự đọc số cân trên **cùng ảnh**:
1. Mặt nạ đỏ `R−(G+B)/2 > 100`.
2. Khu trú màn hình: **dilate + lấy cụm liên thông đỏ lớn nhất** (scipy) → tách nhiễu thùng nâu.
3. Bỏ đốm nhiễu (giữ cụm cột lớn), resize chữ số về cao ~150px, `ssocr -d -1 remove_isolated`.
4. **Chia 10^decimals** (mặc định 2 → `943` = 9.43 kg).
5. Cờ `confident` = ssocr đọc sạch (không ký tự lạ). Chụp **gần** → đọc đúng; **xa** →
   thất bại rõ ràng (không ghi số sai). **Luôn cho user xác nhận/sửa** → Áp dụng vào Gross.
- **Yêu cầu:** cài `ssocr` trên server (`sudo apt-get install ssocr`). ssocr hơi yếu với số **7**.

**Tải tất cả (`download_all_photos`):** nén zip toàn bộ ảnh, tên file trong zip đúng chuẩn.
Nút bị chặn nếu chưa có ảnh nào.

---

## 8. Chốt cartons trước khi chụp

- **Generate khi đã có ảnh:** client hiện **confirm Yes/No**; Yes → `generate_detail(force=1)`
  **xóa toàn bộ File ảnh cũ** rồi tạo lại. Không confirm/không force → server `throw`.
- Lý do: Generate lại đánh số/đổi cấu trúc thùng → ảnh & kg cũ không còn khớp.

---

## 9. Đặt tên & Print Format

- **Tên document = No** (`autoname: format:{no}`). Sửa No → `on_update` gọi `rename_doc`
  đổi tên theo (khác `field:no` vốn khóa field).
- **Print Format "Packing List":** A4 **ngang** (`orientation: landscape` trong `.print-format`),
  label căn trái + value sát label (CSS `.data-field` inline-block — chạy cả wkhtmltopdf),
  cuối trang có bảng **Quantity Summary (size×màu)** render server-side qua Jinja
  `{{ doc.get_size_color_summary_html() | safe }}`.

---

## 10. Server methods (whitelisted)

| Method | Vai trò |
|---|---|
| `generate_detail(doc, force=0)` | Xếp thùng + tổng; chặn/force khi đã có ảnh |
| `apply_mix(doc, cartons)` | Áp dụng chỉnh tay thùng ghép (bảo toàn) |
| `save_carton_photo(packing_list, carton_no, color, size, image)` | Lưu ảnh thùng |
| `download_all_photos(packing_list)` | Zip tải tất cả ảnh |
| `read_scale_ocr(image, decimals=2)` | OCR số cân bằng ssocr |

> ⚠️ Thêm/đổi **method Python** → cần **`bench restart`** (web worker gunicorn `--preload`
> không tự nạp lại code; `clear-cache` chỉ xóa redis). Sửa JS/JSON → `clear-cache` + refresh.

---

## 11. Files
```
doctype/packing_list/               packing_list.{json,py,js}, readme.md
doctype/packing_list_detail/        packing_list_detail.{json,py}
doctype/packing_list_carton_type/   packing_list_carton_type.{json,py}
print_format/packing_list/          packing_list.json
```
Phụ thuộc: `ssocr` (system), `numpy`/`scipy`/`Pillow` (env), Cropper.js (CDN, `app_include_js`).
