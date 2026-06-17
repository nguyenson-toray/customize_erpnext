# Print Format: Stock Entry Material

**Doctype:** Stock Entry · **Loại:** Jinja (Print Format Builder, `print_format_builder = 1`) · **Module:** Customize Erpnext

Phiếu Xuất/Nhập kho dùng chung cho **vải và nhiều loại item khác**. Tiêu đề và cột tự đổi theo loại phiếu (`stock_entry_type`) và theo nội dung item.

> Bố cục được quản lý bằng `format_data` (mảng JSON). Các khối trình bày chính là các phần tử **Custom HTML** (`fieldtype = "HTML"`, `fieldname = "_custom_html"`) chứa Jinja. Khi sửa: chỉnh trong Print Format Builder hoặc sửa `options` của đúng phần tử rồi `export_to_files`.

---

## Các khối HTML (Custom HTML / Jinja)

### 1. Print heading placeholder
- **Vị trí:** phần tử đầu (`fieldname = "print_heading_template"`).
- **Nội dung:** chỉ 1 dấu cách → để **ẩn tiêu đề mặc định** của Frappe (vì đã tự vẽ tiêu đề riêng ở khối Title + QR).

### 2. Company header (đầu trang)
- **Nhận diện:** class `.header-wrap`.
- **Nội dung:** logo công ty (`/assets/customize_erpnext/images/logo_500.jpg`) + tên công ty (Việt + Anh) + địa chỉ. Tĩnh, không phụ thuộc dữ liệu phiếu.

### 3. Title + QR
- **Nhận diện:** class `.heading-wrap`, có `stock_entry_type`.
- **Tiêu đề (đổi theo loại phiếu):**
  ```jinja
  <strong>{% if doc.stock_entry_type == "Material Issue" %}PHIẾU XUẤT KHO{% else %}PHIẾU NHẬP KHO{% endif %}</strong>
  ```
- **Phụ đề tiếng Anh (đổi theo loại phiếu):**
  ```jinja
  <em>{% if doc.stock_entry_type == "Material Issue" %}DELIVERY NOTE{% else %}RECEIPT NOTE{% endif %}</em>
  ```
  | stock_entry_type | Tiêu đề | Phụ đề |
  |---|---|---|
  | Material Issue | PHIẾU XUẤT KHO | DELIVERY NOTE |
  | còn lại (Material Receipt) | PHIẾU NHẬP KHO | RECEIPT NOTE |
- **QR:** ảnh QR (api.qrserver.com) trỏ tới URL phiếu: `{{ frappe.utils.get_url() }}/app/stock-entry/{{ doc.name }}` (đã `| urlencode`).

### 4. Số phiếu (No)
- **Nội dung:** `No: {{ _(doc.name) }}` — hiển thị tên/số phiếu (đã đổi sang naming `{custom_name}.-.####`, ví dụ `PN2606-0001`).

### 5. Items table (Chi tiết / Items) — khối chính
- **Nhận diện:** bảng có cột `Mã vật tư` … `ĐVT`.
- **Cột:** STT · Mã vật tư · Tên vật tư · Màu · Kích thước · Mô tả · Số hóa đơn · **[Lô | Cuộn]** · SL · ĐVT.
- **Màu / Kích thước:** lấy từ `Item.attributes` (attribute "Color" / "Size"), bỏ qua giá trị rỗng (`Blank`, `N/A`, `-`, `""`).
- **⭐ Cơ chế "mỗi batch 1 dòng" (khác `PXK Vai`):**
  - Item **không** batch → **1 dòng**, SL = `row.qty`.
  - Item **có** batch → **mỗi batch xuất ra 1 dòng riêng**; mỗi dòng lặp lại thông tin item + `lot|roll` của batch đó + **SL của riêng batch** (lấy từ `Serial and Batch Entry.qty`, dùng `| abs`).
  - `STT` đánh số **theo từng dòng hiển thị** (tăng qua cả các dòng batch).
  - Ví dụ: 1 item có 6 batch → in ra 6 dòng.
- **Cột "Lô | Cuộn" (Lot | Roll) — có điều kiện:**
  - Trước khi vẽ bảng, quét `doc.items`; đặt cờ `show_batch = true` nếu **có ≥1 item `has_batch_no`**.
  - Header, ô dữ liệu và `colspan` của dòng **Total** (8 nếu có batch, 7 nếu không) chỉ render khi `show_batch` → **phiếu toàn item không batch sẽ tự ẩn cột** (dùng chung 1 format).
  - **Lấy batch mỗi dòng:** ưu tiên `row.batch_no`; nếu không có thì đọc `Serial and Batch Entry` theo `row.serial_and_batch_bundle`.
  - **Hiển thị:** `lot|roll` lấy từ `Batch.custom_lot_number` + `Batch.custom_roll_number` (vd `54|4`). Fallback về `batch_no` nếu batch thiếu lot number.
- **Dòng Total:** chỉ hiện khi toàn bảng dùng **cùng 1 ĐVT** (`unique_uoms | length == 1`); cộng dồn SL của **tất cả các dòng** (gồm từng dòng batch).

> **So sánh với `PXK Vai`:** `PXK Vai` gộp nhiều batch trong **1 ô** (1 dòng/item, các batch xuống dòng `<br>`, không kèm SL/batch). `Stock Entry Material` tách **1 dòng/batch** kèm SL từng batch.

### 6. Bảng chữ ký (cuối phiếu)
- **Nhận diện:** class `.sig-table`.
- **3 cột ký:** Người lập phiếu (*Issued by*) · Người nhận (*Deliverer*) · Thủ kho (*Warehouse keeper*). Tĩnh.

---

## Các trường bind trực tiếp (không phải HTML)
`custom_material_issue_purpose`, `custom_fg_qty`, `custom_line`, `custom_fg_color`, `custom_fg_style`, `custom_fg_size`, `posting_date` (Ngày/Date), `custom_note` (Note), `from_warehouse` (Kho xuất), `to_warehouse` (Kho nhập), `letter_head`.

---

## Cập nhật / Export
Khi sửa `options` của một khối qua script:
```python
import frappe, json
doc = frappe.get_doc("Print Format", "Stock Entry Material")
fd = json.loads(doc.format_data)
# ... sửa fd[idx]["options"] ...
doc.format_data = json.dumps(fd, ensure_ascii=False)
doc.save(ignore_permissions=True); frappe.db.commit()
from frappe.modules.export_file import export_to_files
export_to_files(record_list=[["Print Format", "Stock Entry Material"]], record_module="Customize Erpnext")
```
> Lưu ý: thứ tự/chỉ số phần tử trong `format_data` thay đổi mỗi khi sửa qua Builder — **định vị khối theo nội dung** (vd chứa `Mã vật tư`, `heading-wrap`, `sig-table`), không hardcode index.
