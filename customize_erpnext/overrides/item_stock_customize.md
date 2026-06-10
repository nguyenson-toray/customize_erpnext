# Item & Stock Customizations — TIQN ERPNext

Tổng hợp toàn bộ customization liên quan Item và Stock trong app `customize_erpnext`.

---

## Mục lục

1. [hooks.py — Đăng ký & Doc Events](#1-hookspy)
2. [Item Form (item.js)](#2-item-form-itemjs)
3. [Item — Multiple Variants Dialog](#3-item--multiple-variants-dialog)
4. [Item List View (item_list.js)](#4-item-list-view-item_listjs)
5. [Item Attribute (item_attribute.js)](#5-item-attribute-item_attributejs)
6. [Item Attribute Import (item_attribute_import.js)](#6-item-attribute-import-item_attribute_importjs)
7. [Stock Entry Form (stock_entry.js)](#7-stock-entry-form-stock_entryjs)
8. [Stock Entry — Quick Import (stock_entry_quick_import.js)](#8-stock-entry--quick-import-stock_entry_quick_importjs)
9. [Stock Entry List View (stock_entry_list.js)](#9-stock-entry-list-view-stock_entry_listjs)
10. [Stock Reconciliation (stock_reconciliation.js)](#10-stock-reconciliation-stock_reconciliationjs)
11. [Material Request (material_request.js)](#11-material-request-material_requestjs)
12. [BOM (bom.js)](#12-bom-bomjs)
13. [Python — Stock Ledger Propagation](#13-python--stock-ledger-propagation)
14. [Python — BOM API](#14-python--bom-api)
15. [Python — Item Attribute Import](#15-python--item-attribute-import)
16. [Custom Fields & Fixtures](#16-custom-fields--fixtures)
17. [Batch — cuộn vải (batch.js + batch_utils.py)](#17-batch--cuộn-vải)
18. [Reports — Stock Balance / Stock Ledger Customize](#18-reports)
19. [Power Query API — Stock Balance (guest)](#19-power-query-api)

---

## 1. hooks.py

### doctype_js (Client scripts)

| DocType | File(s) |
|---|---|
| Stock Entry | stock_entry.js, stock_entry_quick_import.js, serial_batch_selector_custom.js |
| BOM | bom.js |
| Item | item.js, item_show_multiple_variants_dialog.js |
| Material Request | material_request.js |
| Item Attribute | item_attribute.js, item_attribute_import.js |
| Item Attribute Value | item_attribute.js |
| Stock Reconciliation | stock_reconciliation.js |
| Batch | batch.js |

### doctype_list_js (List view scripts)

| DocType | File |
|---|---|
| Item | item_list.js |
| Stock Entry | stock_entry_list.js |

### doc_events (Python hooks)

| DocType | Event | Handler |
|---|---|---|
| Stock Entry | on_submit | `update_stock_ledger_invoice_number_receive_date` |
| Stock Reconciliation | on_submit | `update_stock_ledger_invoice_number_receive_date` |
| Batch | before_insert | `api.batch.batch_utils.set_batch_defaults` (auto batch_id + custom_color) |
| Item | validate | *(commented out — barcode auto-add đã tắt)* |

### data_import hooks

- `data_import_before_import`: `customize_erpnext.override_methods.item_attribute_import.before_import`

### Fixtures được export

- **Custom Field**: Stock Entry, Stock Entry Detail, Stock Reconciliation, Stock Reconciliation Item, Stock Ledger Entry, Item, **Batch**, ...
- **Property Setter**: Item, Stock Entry Detail, Stock Reconciliation, Stock Reconciliation Item
- **List View Settings**: Item, Stock Entry, Stock Reconciliation
- **Report**: Stock Ledger Customize, Stock Balance Customize *(Stock Ageing Customize đã gỡ bỏ — ageing nằm trong Stock Balance Customize)*
- **Workspace Sidebar**: Stock

---

## 2. Item Form (item.js)

### Item Code tự động sinh

Khi tạo Item mới, hệ thống tự sinh `item_code` dựa trên `item_group`:

| Prefix | Item Group | Kiểu mã |
|---|---|---|
| B- | B-Finished Goods | Base-36 3 ký tự (0-9, A-Z) |
| C- | C-Fabric | Base-36 3 ký tự |
| D- | D-Interlining | Base-36 3 ký tự |
| E- | E-Padding | Base-36 3 ký tự |
| F- | F-Packing | Base-36 3 ký tự |
| G- | G-Sewing Accessories | Base-36 3 ký tự |
| H- | H-Thread | Base-36 3 ký tự |
| O- | O-Office | 4 chữ số số học (0001, 0002, ...) |
| T- | T-Tools | Base-36 3 ký tự |
| A- | A-Assets | Base-36 3 ký tự |
| U- | U-Uniform | Base-36 3 ký tự |

Thuật toán: query item_code lớn nhất theo prefix → increment base-36 → gán vào field.

**Duplicate detection**: Gọi `is_exists_item(item_group, item_name)` trước khi tạo để tránh trùng.

### Default configs theo Item Group

Mỗi nhóm có bộ default riêng khi chọn `item_group`:
- `stock_uom`: mặc định "Pcs" hoặc theo nhóm
- `has_variants`: 1 cho B/C/D/E/F/G/H/T, 0 cho O/A
- `is_purchase_item`, `is_sales_item`, `is_customer_provided_item`: phụ thuộc nhóm
- `item_group` change bị hạn chế sau khi đã lưu, trừ nhóm U-Uniform

### Default Warehouse logic

- B-Finished Goods → `'Finished Goods - TIQN'`
- `is_customer_provided_item = 1` → lấy `Customer.custom_default_warehouse` → fallback `'Material - Local - TIQN'`
- Các nhóm khác: xem theo cấu hình item defaults

### Buttons thêm vào form

- **'Single Variant'** button: bị **xóa khỏi** Create menu
- **'Update Default Warehouse'** button: thêm vào Actions menu → gọi API `customize_erpnext.api.utilities.set_default_warehouse_by_brand`

### create_attributes()

Khi `has_variants = 1`, tự động thêm 4 attributes: `Color`, `Size`, `Brand`, `Season` — trừ các nhóm: O-Office, Factory, Tools, Assets.

---

## 3. Item — Multiple Variants Dialog

**File**: `item_show_multiple_variants_dialog.js`
**Override**: `erpnext.item.show_multiple_variants_dialog`

### Thứ tự attribute cố định

`['Color', 'Size', 'Brand', 'Season', 'Info']`

### Proper Case conversion

Toàn bộ attribute values được convert sang Proper Case trước khi lưu (VD: `"RED"` → `"Red"`).

### Fuzzy matching — cảnh báo giá trị tương tự

Thuật toán Levenshtein distance với ngưỡng `0.7`. Nếu giá trị mới gần giống giá trị đã có → cảnh báo trùng.

### Bulk input

Textarea nhập nhiều dòng, Ctrl+Enter để áp dụng.

### Import Missing Values button

Thêm values còn thiếu vào `Item Attribute` qua `frappe.client.save`.

### Update Attribute Values button

Refresh dialog mà không mất các selection đã chọn.

### Batch variant creation

Tạo variants theo batch `batch_size = 10` với progress dialog hiển thị %.

### Sau khi tạo variants

Gọi `customize_erpnext.api.utilities.set_default_warehouse_by_brand` với `BRAND_WAREHOUSE_MAP`:

| Brand | Warehouse |
|---|---|
| Ariake, Mizuno, Shimano, Snow Peak, Tnf | JP warehouse |
| Các brand khác | HK warehouse |

---

## 4. Item List View (item_list.js)

### Print QR Labels

- Filter dialog: custom / recent / all items
- Preview table: danh sách items cần in
- Add-to-list: thêm item vào danh sách in
- PDF generation: `customize_erpnext.api.qr_label_print.generate_qr_labels_pdf`
- Page formats: `a5_landscape` hoặc `a4_tommy`

### Quick Check Item

- Scanner QR code (Html5QrcodeScanner từ CDN) hoặc search theo item code
- Hiển thị: item info + stock từ Bin + 20 giao dịch SLE gần nhất

### Export Master Data — Item Attribute

- Gọi `customize_erpnext.api.utilities.export_master_data_item_attribute`
- Tải xuống file Excel

### Create Item Variants From Excel

1. Validate: `create_item_variants_improved_validate_data`
2. Tạo: `create_item_variants_improved`

### Row indicator màu

| Trạng thái | Màu |
|---|---|
| Disabled | Xám |
| Stock Item | Xanh lá |
| Non-Stock Item | Cam |

---

## 5. Item Attribute (item_attribute.js)

### Before save

- Convert tất cả `attribute_value` sang **Proper Case**
- Validate format `abbr` theo loại attribute:
  - Color, Size, Info: 3 ký tự `[0-9A-Z]`
  - Brand, Season: 2 ký tự `[0-9A-Z]`
- Duplicate check toàn bộ attributes (case-insensitive) trước khi lưu

### Khi thêm dòng mới

Auto-generate `abbr` tiếp theo (base-36 increment từ `abbr` cuối cùng).

### On `attribute_value` change

Auto-convert sang Proper Case ngay lập tức.

### On `abbr` change

Validate format và cảnh báo nếu trùng với abbr khác.

---

## 6. Item Attribute Import (item_attribute_import.js)

### "Import Values" button trên Item Attribute form

1. Paste nhiều giá trị (mỗi dòng một giá trị)
2. Deduplicate + convert sang Proper Case
3. Real-time preview trước/sau Proper Case conversion
4. Auto-generate `abbr` tiếp theo từ `abbr` cuối cùng
5. Import với progress bar

### Patch Data Import form

Thêm hướng dẫn CSV format cho Item Attribute khi user mở Data Import.

### Python — `get_last_abbreviation`

API: `customize_erpnext.override_methods.item_attribute_import.get_last_abbreviation`

- Trả về `abbr` cuối cùng của attribute đã có
- Default: `"000"` cho Color/Size/Info, `"00"` cho Brand/Season

### Python — `fix_missing_abbreviations`

Chạy sau khi import qua Data Import — tự động sinh `abbr` cho các values bị thiếu.

---

## 7. Stock Entry Form (stock_entry.js)

### Hạn chế loại giao dịch

Chỉ cho phép:
- Material Receipt
- Material Issue
- Material Transfer

Các loại khác → `frappe.throw()`.

### Validate pipeline (trước khi lưu)

1. Xóa các dòng items rỗng
2. Trim parent fields
3. Trim `custom_invoice_number` trong child rows
4. Validate / auto-fill warehouses
5. Aggregate invoice numbers
6. Sync fields từ parent xuống child

### Before submit validation

1. Validate invoice numbers (có option auto-fill)
2. Validate `custom_no`
3. Validate `custom_receive_date` (bắt buộc cho Opening Stock Material Receipt)
4. Set `custom_note` cho opening stock

### Invoice Selector

- Click vào `custom_invoice_number` trong dòng Material Issue / Transfer
- Dialog hiển thị tồn kho theo từng invoice number
- Multi-select + FIFO allocation tự động

### Add Multiple Batch (serial_batch_selector_custom.js)

Override `erpnext.SerialBatchPackageSelector` (patch prototype, idempotent). Thêm nút **"Add Multiple Batch"** ngay sau section *"Add Batch Nos via CSV File"* trong dialog "Add Batch Nos".
- Phạm vi: **Stock Entry** + item **có batch, không serial** + giao dịch **Inward** (`get_attach_field`).
- Mở dialog phụ: nạp **tất cả Batch của item** (`disabled=0`), **lọc** theo Batch/Lot/Roll/Color, chọn **1 / nhiều / tất cả** (Select All / Clear All), cột **Quantity** điền sẵn từ `custom_initial_quantity` (sửa được) + ô **Default Quantity** cho dòng trống.
- **Add Selected** → push `{batch_no, qty}` vào bảng `entries` của dialog gốc (trùng batch thì cập nhật Qty), dùng đúng pattern `fields_dict.entries.df.data` + `grid.refresh()`.

### Warehouse auto-fill

Khi chọn `item_code` trong child row:
- Material Issue / Transfer: auto-fill `s_warehouse` từ item defaults
- Material Receipt: auto-fill `t_warehouse` từ item defaults

### sync_fields_to_child_table

Sync từ parent xuống tất cả child rows:
- `custom_material_issue_purpose`
- `custom_line`
- `custom_fg_qty`, `custom_fg_style`, `custom_fg_color`, `custom_fg_size`

### Warehouse column visibility

Hiển thị / ẩn columns `s_warehouse`, `t_warehouse`, `custom_receive_date` động theo `stock_entry_type`.

### custom_is_opening_stock

- Alert người dùng điền `receive_date`
- Auto-generate `custom_no` dạng: `'Opening Stock {date} {3-random-digits}'`

### Work order warning

Kiểm tra nếu đã tồn tại "Material Transfer for Manufacture" entries → hiển thị warning trong dashboard.

---

## 8. Stock Entry — Quick Import (stock_entry_quick_import.js)

### Duplicate Selected (grid button)

- Shortcut: `Ctrl+D`
- Duplicate các dòng đang chọn trong grid

### Import Material Issue (Actions button)

Chỉ hiện với `stock_entry_type = 'Material Issue'`:
1. Download Excel template: `create_material_issue_template.create_material_issue_template`
2. Validate file: `create_material_issue.validate_excel_file`
3. Import: `create_material_issue.import_material_issue_from_excel`

### Quick Add — Material Issue

**Format**: `item_name_detail; invoice_number; qty; [customs_declaration_number]`

- Tối đa 200 dòng
- Tìm kiếm theo `custom_item_name_detail` trên Item variants (`variant_of != ''`)
- Hỗ trợ số định dạng Việt Nam (dấu phẩy là dấu thập phân)
- Progress dialog với % hoàn thành
- Sau khi thêm: verify qty đúng

### Quick Add — Material Receipt

**Format**: `item_name_detail; invoice_number; qty; [customs_declaration_number]`

- Tương tự Material Issue
- Tối đa 200 dòng

---

## 9. Stock Entry List View (stock_entry_list.js)

### Import Stock Entry — Material Issue (List Actions)

1. Download template Excel
2. Upload file Excel
3. Validate (progress bar animation, kết quả được cache):
   - Hiển thị: missing items + suggestions, missing warehouses, stock issues
4. Import → Hiển thị bảng entries đã tạo với links

API pattern: `create_material_issue.*`

### Import Stock Entry — Material Receipt (List Actions)

Tương tự Material Issue, dùng `create_material_receipt.*`

---

## 10. Stock Reconciliation (stock_reconciliation.js)

### Opening Stock — Quick Add

**Format**: `item_name_detail; invoice_number; qty; receive_date; [customs_declaration_number]`

- Tối đa **3000 dòng** (lớn hơn nhiều so với Stock Entry)
- Validate date: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD; tối đa 1 năm trong tương lai
- Xử lý theo batch:
  - Search: 500 items/batch
  - Item details: 300/batch
  - Add to grid: 200/batch
- Tự set `allow_zero_valuation_rate = 1`
- Button chỉ hiện khi `purpose = 'Opening Stock'`

### Invoice Selector (Stock Reconciliation purpose)

- Tương tự stock_entry: `get_stock_by_invoice.get_stock_by_invoice`
- Các dòng thêm vào có `qty = 0` (điền thủ công)
- Set `custom_receive_date` từ invoice được chọn

### Duplicate Selected

- Shortcut: `Ctrl+D`
- Button chỉ hiện khi có rows đang chọn

### before_submit validation

- `custom_receive_date`: format hợp lệ, không rỗng
- `custom_invoice_number`: không rỗng
- `qty > 0`

### validate

Xóa các dòng items rỗng.

### Purpose handler

Khi `purpose = 'Opening Stock'`:
- Set `posting_time = '00:00:00'`
- Field `posting_time` thành read-only

---

## 11. Material Request (material_request.js)

### Active feature

**Sum Qty Of Duplicate Item** button (chỉ khi `docstatus = 0`):
- Gọi `customize_erpnext.api.material_request.sum_duplicate_items`
- Gộp qty các dòng cùng item thành 1 dòng

### Commented out (tạm thời tắt)

- `validate_total_amount`: routing phê duyệt theo ngưỡng (0 / <20M VND / ≥20M VND)
- `show_production_plan_dialog`
- `show_split_dialog`
- `show_work_order_dialog`

---

## 12. BOM (bom.js)

### Copy For All Size — Same Color

Button gọi `customize_erpnext.api.bom.copy_bom_for_same_color`:
- Copy BOM hiện tại sang tất cả variants cùng `variant_of` và cùng `Color`
- Items có `custom_is_difference = 1` → thêm intro cảnh báo "Need to review" màu cam

### Row color coding theo item code prefix

| Prefix | Màu nền | Nhóm |
|---|---|---|
| C- | `#f0fff0` (honeydew) | Fabric |
| D- | `#e6e6fa` (lavender) | Interlining |
| E- | `#f5f5f5` (whitesmoke) | Padding |
| F- | `#f5fffa` (mintcream) | Packing |
| G- | `#dcdcdc` (gainsboro) | Sewing |
| H- | `#e0ffff` (lightcyan) | Thread |

### Định dạng đặc biệt

- `custom_is_difference = 1`: **in đậm màu đỏ**
- Qty nguyên (integer): **in đậm màu xanh**
- Fix bug hiển thị VND trong `custom_total_qty`

---

## 13. Python — Stock Ledger Propagation

**File**: `api/stock_ledger/update_stock_ledger_invoice_number_receive_date.py`

**Trigger**: `on_submit` của Stock Entry và Stock Reconciliation (via `doc_events` trong hooks.py)

### Mục đích

Sau khi submit, copy `custom_invoice_number` và `custom_receive_date` từ child items → các `Stock Ledger Entry` tương ứng.

### Chiến lược match SLE ↔ Item row

1. **Primary**: Match qua `voucher_detail_no` (chính xác nhất)
2. **Fallback**: Sequential mapping theo `(item_code, warehouse, transaction_type)`
   - `transaction_type = 'in'` nếu `actual_qty > 0`, ngược lại `'out'`
   - Best-match theo qty, nếu không tìm được thì lấy item đầu tiên còn lại

### Fields được set trên SLE

- `custom_invoice_number`
- `custom_receive_date`
- `custom_is_opening_stock` (từ Stock Entry parent; luôn `0` cho Stock Reconciliation)

### Batch update

Dùng raw SQL `UPDATE tabStock Ledger Entry SET ... WHERE name = %s` + `frappe.db.commit()`.

### Utility functions khác

- `get_stock_balance_with_custom_fields(filters)`: Query SLE với filter theo invoice/receive_date, group by item+warehouse+invoice+date
- `validate_custom_fields_consistency()`: Kiểm tra tính nhất quán giữa SE/SR items và SLE
- `fix_missing_custom_fields_in_sle(filters)`: Retroactively update các SLE bị thiếu custom fields

---

## 14. Python — BOM API

**File**: `api/bom.py`

### `copy_bom_for_same_color(doc)`

- Whitelist API
- Input: BOM document (JSON hoặc dict)
- Lấy `Color` attribute từ source item
- Tìm tất cả variants cùng `variant_of` + cùng `Color` → copy BOM cho từng item
- Set `custom_item_name_bom` trên BOM mới
- Return: danh sách BOM names đã tạo

### `get_item_name_for_bom(item_code)`

Whitelist API — trả về `item_name` từ `item_code`.

### `get_item_attribute(item_code)`

Whitelist API — trả về dict `{attribute_lower: attribute_value}` cho Item variant.

---

## 15. Python — Item Attribute Import

**File**: `override_methods/item_attribute_import.py`

### `get_last_abbreviation(attribute_name)` (whitelist)

Trả về `abbr` cuối cùng của attribute:
- Lấy danh sách `Item Attribute Values`, sort theo `idx`, trả về `abbr` của dòng cuối
- Default: `"000"` cho Color/Size/Info; `"00"` cho Brand/Season

### `get_next_code(max_code)`

Sinh mã tiếp theo theo base-36 (0-9, A-Z):
- Hỗ trợ 2 hoặc 3 ký tự
- Tự động carry over: `Z9 → ZA`, `ZZ → 00` (reset)

### `before_import(data_import_doc)` (hook)

Chạy trước Data Import cho Item Attribute — hiển thị thông báo.

### `after_import(data_import_doc)` (hook)

Chạy sau Data Import — gọi `fix_missing_abbreviations` để tự sinh `abbr` cho các dòng thiếu.

---

## 16. Custom Fields & Fixtures

### Custom fields trên Stock Entry Detail

| Field | Type | Mô tả |
|---|---|---|
| `custom_invoice_number` | Data | Số invoice nhập hàng |
| `custom_receive_date` | Date | Ngày nhận hàng |
| `custom_material_issue_purpose` | Data | Mục đích xuất kho (sync từ parent) |
| `custom_line` | Data | Dây chuyền (sync từ parent) |
| `custom_fg_qty` | Float | Qty thành phẩm (sync từ parent) |
| `custom_fg_style` | Data | Style thành phẩm |
| `custom_fg_color` | Data | Màu thành phẩm |
| `custom_fg_size` | Data | Size thành phẩm |

### Custom fields trên Stock Reconciliation Item

| Field | Type | Mô tả |
|---|---|---|
| `custom_invoice_number` | Data | Số invoice |
| `custom_receive_date` | Date | Ngày nhận hàng |

### Custom fields trên Stock Ledger Entry

| Field | Type | Mô tả |
|---|---|---|
| `custom_invoice_number` | Data | Propagated từ SE/SR |
| `custom_receive_date` | Date | Propagated từ SE/SR |
| `custom_is_opening_stock` | Check | Đây là khai báo kho ban đầu |

### Custom fields trên Stock Entry (parent)

| Field | Type | Mô tả |
|---|---|---|
| `custom_is_opening_stock` | Check | Khai báo tồn kho ban đầu |
| `custom_no` | Data | Số tham chiếu nội bộ |
| `custom_material_issue_purpose` | Data | Mục đích xuất kho |
| `custom_line` | Data | Dây chuyền sản xuất |
| `custom_fg_qty/style/color/size` | Various | Thông tin thành phẩm |
| `custom_total_qty` | Float | Tổng qty |

### Custom fields trên Item

| Field | Type | Mô tả |
|---|---|---|
| `custom_item_name_detail` | Data | Tên chi tiết dùng trong Quick Add |

### Custom fields trên Batch

| Field | Type | Mô tả |
|---|---|---|
| `custom_lot_number` | Data | Số lô (NCC) — thành phần `lot` của batch_id |
| `custom_roll_number` | Data | Số cuộn — thành phần `roll` của batch_id |
| `custom_color` | Data (read-only) | Màu, tự điền từ thuộc tính Color của item (hook `set_batch_defaults`) |
| `custom_initial_quantity` | Float | "Initial Quantity" — SL dự kiến (vd chiều dài cuộn). Dùng điền sẵn Quantity khi "Add Multiple Batch". **KHÔNG** tự tạo tồn (khác `batch_qty` read-only do hệ thống tính từ Stock Ledger) |

> Patch: `add_batch_custom_fields` (lot/roll), `add_batch_color_field` (color), `add_batch_initial_qty_field` (initial qty). Fixtures Custom Field bao gồm `Batch`.

---

## 17. Batch — cuộn vải

**Client:** `public/js/custom_scripts/batch.js` · **Server:** `api/batch/batch_utils.py`

### Quy ước batch_id
```
batch_id = {template_item_name}|{color}|{lot}|{roll}   (| đơn, color bỏ qua nếu item không có Color)
```
- `template_item_name` = `item_name` của template (`variant_of`); `color` = thuộc tính Color của variant.
- **lot/roll giữ nguyên như nhập (số hoặc text), KHÔNG pad số 0.**
- C-Fabric: `has_batch_no=1`, `create_new_batch=0` → batch phải tạo trước khi nhập kho.

### batch.js (form Batch)
- Nút **Generate Batch ID** (chỉ khi new): gọi `get_batch_id_components(item_code)` → dựng batch_id + set `custom_color`.
- Đổi `item` / `custom_lot_number` / `custom_roll_number` → xoá `batch_id` để buộc generate lại.

### batch_utils.py
| Hàm | Vai trò |
|---|---|
| `get_batch_id_components(item_code)` | whitelist; trả `{template_name, color}` cho nút Generate |
| `_get_template_and_color(item_code)` | (template item_name, Color attr value) |
| `build_batch_id(template, color, lot, roll)` | ghép batch_id `|` đơn, không pad |
| `set_batch_defaults(doc, method)` | **hook Batch.before_insert** |

### Hook `set_batch_defaults` (before_insert)
- Luôn set `custom_color` từ Color của item.
- Nếu `batch_id` trống mà có item + lot + roll → tự sinh `batch_id` (rule trên).
- Chạy **trước** `set_new_name()` nên batch_id tự sinh trở thành tên Batch (autoname `field:batch_id`).
- ⇒ **Import Excel/Data Import** chỉ cần `item`, `custom_lot_number`, `custom_roll_number` (để trống `batch_id`); nếu điền sẵn `batch_id` thì giữ nguyên.

---

## 18. Reports

### Stock Balance Customize
**File:** `report/stock_balance_customize/stock_balance_customize.{py,js}` — class `StockBalanceReportCustomized`, `CustomizedFIFOSlots`.

| Khả năng | Ghi chú kỹ thuật |
|---|---|
| Group by Invoice Number | gom theo `custom_invoice_number` (mặc định bật) |
| Group by Batch (+ Lot/Roll) | v16 lưu batch trong **Serial and Batch Bundle** (`sle.batch_no` NULL) → `_expand_entries_by_batch()` tách mỗi SLE-bundle thành 1 dòng/batch (qty có dấu từ `Serial and Batch Entry`); cột Lot/Roll lấy từ `custom_lot_number`/`custom_roll_number` qua `_get_batch_lot_roll_map()` |
| Show Variant Attributes | chỉ Color/Size/Brand/Season/Info (bỏ attribute rác như `Colour`) |
| Show Stock Ageing Data | dải tuổi FIFO; ưu tiên `custom_receive_date` hơn `posting_date` (`CustomizedFIFOSlots`) |
| Include Zero Stock Items | hiện cả tồn 0 |
| Item / Warehouse | **MultiSelectList** (chọn nhiều) — backend `.isin()` |
| ~~Batch No filter~~, ~~Include UOM~~ | **đã gỡ khỏi UI** |

> Fix v16: import `get_serial_nos_from_bundle` từ `erpnext.stock.serial_batch_bundle` (KHÔNG dùng module test — trước đây gây crash → report trống).

### Stock Ledger Customize
**File:** `report/stock_ledger_customize/stock_ledger_customize.py`
- `enrich_batch_info()` điền cột **Batch No** từ Serial and Batch Bundle: 1 phiếu nhiều cuộn → danh sách cuộn (phẩy); lọc 1 Batch No → chỉ cuộn đó, In/Out & Balance tính riêng (`get_batch_opening_qty` + running balance per-roll).
- Cột Batch No đổi `Link`→`Data`; bỏ attribute rác (giống Stock Balance).

### Stock Ageing Customize — ĐÃ GỠ BỎ
Trùng với phần ageing của Stock Balance Customize → xoá cả Report record lẫn thư mục `report/stock_ageing_customize/`.

---

## 19. Power Query API

**File:** `api/stock/stock_balance_api.py` · **Endpoint (GET, `allow_guest=True`):**
```
/api/method/customize_erpnext.api.stock.stock_balance_api.get_stock_balance
```
Trả về kết quả **Stock Balance Customize** dạng JSON (mảng record keyed theo nhãn cột) cho Excel/Power Query.

### Tham số & mặc định
| Param | Mặc định |
|---|---|
| `from_date` | đầu năm tài chính 01/04 (tháng 4–12 → năm nay; tháng 1–3 → năm trước) |
| `to_date` | today |
| `warehouse` | null = tất cả |
| `item_group` | null = tất cả |
| `show_variant_attributes` | true |
| `summary_qty_by_invoice_number` | true |
| `group_by_batch` | true |
| `show_stock_ageing_data` | false |
| `include_zero_stock_items` | true |
| `company` | Global Defaults → default_company |

`company` tự lấy default; bool nhận `1/true/yes/on`. Hàm gọi thẳng `execute(filters)` của report rồi flatten theo `(fieldname → label)`.

> ⚠️ **Bảo mật:** `allow_guest=True` = không cần đăng nhập → nên giới hạn ở tầng mạng/proxy (VPN, firewall, IP allow-list) nếu dữ liệu nhạy cảm.

### Power Query (M)
```m
let
    url  = "https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.stock.stock_balance_api.get_stock_balance",
    resp = Json.Document(Web.Contents(url, [Query=[to_date="2026-06-09"]])),
    rows = resp[message],
    tbl  = Table.FromRecords(rows)
in
    tbl
```

---

## Luồng dữ liệu tổng quan

```
[Item Attribute]
  └─ Proper Case, abbr validation, bulk import

[Item]
  └─ Auto item_code (base-36 / numeric)
  └─ Default configs per group
  └─ Attribute auto-add (Color/Size/Brand/Season)

[Multiple Variants Dialog]
  └─ Proper Case, fuzzy warning, batch creation
  └─ set_default_warehouse_by_brand → Item Default

[Batch (cuộn vải)]
  └─ batch_id = template|color|lot|roll (không pad)
  └─ before_insert: set_batch_defaults → auto batch_id + custom_color (Excel import)

[Stock Entry / Stock Reconciliation]
  │   custom_invoice_number, custom_receive_date (per row)
  │   Serial and Batch Bundle (cuộn vải, v16)
  │   on_submit →
  └─ [Stock Ledger Entry]
       custom_invoice_number
       custom_receive_date
       custom_is_opening_stock

[Reports]
  ├─ Stock Balance Customize  (batch từ bundle + Lot/Roll, ageing, invoice)
  └─ Stock Ledger Customize   (batch từ bundle)
        │
        └─ [Power Query API] get_stock_balance (guest) → Excel

[BOM]
  └─ copy_bom_for_same_color (Python)
  └─ Row coloring by item prefix (JS)
```
