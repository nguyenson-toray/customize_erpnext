# Hướng dẫn Import Material Issue Stock Entry

## Tổng quan
Chức năng import hàng loạt Material Issue (phiếu xuất kho) từ file Excel vào ERPNext.

## Cấu trúc file Excel

### Cột bắt buộc:
- `custom_item_name_detail`: Tên chi tiết item (phải khớp chính xác trong Item master)
- `custom_no`: Mã nhóm (các dòng cùng mã sẽ tạo thành 1 Stock Entry)
- `qty`: Số lượng xuất (số dương)
- `custom_invoice_number`: Số hóa đơn/chứng từ
- `custom_material_issue_purpose`: Mục đích xuất kho (Adjust, Deffected, Destroy, Gap, Ie, Md, Over, Pro, Pro Return, Sample, Trimcard)

### Cột tùy chọn:
- `No`: Số thứ tự
- `posting_date`: Ngày xuất (YYYY-MM-DD)
- `posting_time`: Giờ xuất (HH:MM:SS)
- `s_warehouse`: Kho nguồn (để trống = dùng kho mặc định)
- `custom_fg_style`: Style thành phẩm
- `custom_fg_size`: Size thành phẩm  
- `custom_fg_qty`: Số lượng thành phẩm
- `custom_line`: Chuyền sản xuất
- `custom_fg_color`: Màu thành phẩm
- `custom_note`: Ghi chú

## Logic chọn kho (s_warehouse)

1. **Có s_warehouse trong Excel** → Kiểm tra tồn tại → Dùng kho đó
2. **Không có s_warehouse** → Dùng default warehouse từ Item Default
3. **Cả 2 đều không có** → Báo lỗi

## Quy trình xử lý

### 1. Validation
- Kiểm tra cột bắt buộc
- Kiểm tra item tồn tại
- Kiểm tra warehouse hợp lệ
- Kiểm tra qty > 0
- Kiểm tra material_issue_purpose hợp lệ

### 2. Import
- Group theo `custom_no`
- Tạo Stock Entry cho mỗi nhóm
- Purpose = "Material Issue"
- Dùng `s_warehouse` (kho nguồn)
- Sync finished goods fields từ parent xuống items

### 3. Tối ưu
- **Batch processing**: Xử lý nhiều item cùng lúc
- **Caching**: Cache item và warehouse để tăng tốc
- **Progress tracking**: Hiển thị tiến trình cho user
- **Stock validation**: Kiểm tra tồn kho (có thể disable để tăng performance)

## Khác biệt với Material Receipt

| Material Issue | Material Receipt |
|----------------|------------------|
| Purpose: "Material Issue" | Purpose: "Material Receipt" |
| Dùng `s_warehouse` (kho nguồn) | Dùng `t_warehouse` (kho đích) |
| Xuất kho | Nhập kho |
| Có `custom_material_issue_purpose` | Có `custom_receive_date` |
| Có finished goods fields | Không có finished goods fields |
| Cần kiểm tra tồn kho | Không cần kiểm tra tồn kho |

## Finished Goods Fields

Các trường này được sync từ parent Stock Entry xuống từng item:
- `custom_fg_style` → `custom_fg_style` (item level)
- `custom_fg_size` → `custom_fg_size` (item level)
- `custom_fg_qty` → `custom_fg_qty` (item level)
- `custom_line` → `custom_line` (item level)
- `custom_fg_color` → `custom_fg_color` (item level)

Áp dụng title case formatting cho: custom_line, custom_fg_style, custom_fg_color, custom_fg_size

## File cấu trúc

```
customize_erpnext/
├── api/bulk_update_scripts/
│   ├── create_material_issue.py               # Logic chính
│   ├── create_material_issue_template.py      # Phục vụ template
│   └── create_material_issue_teamplate.xlsx   # File Excel mẫu
└── public/js/custom_scripts/
    └── stock_entry_list.js                   # Giao diện
```

## Cách sử dụng

1. **Tải template**: Click "Download Template" để tải file Excel mẫu
2. **Điền dữ liệu**: Thay thế data mẫu bằng data thật
3. **Upload & Validate**: Upload file và validate dữ liệu
4. **Import**: Nếu validation OK, click "Import" để tạo Stock Entry

## Ví dụ grouping

```excel
custom_no | custom_item_name_detail | qty | custom_material_issue_purpose | custom_invoice_number
PX001     | Item A                 | 100 | Pro                          | INV-001
PX001     | Item B                 | 50  | Pro                          | INV-001
PX002     | Item C                 | 75  | Sample                       | INV-002
```

Kết quả:
- PX001 → 1 Stock Entry với 2 items (Purpose: Pro)
- PX002 → 1 Stock Entry với 1 item (Purpose: Sample)

## Ví dụ warehouse

```excel
custom_item_name_detail | s_warehouse      | Kết quả
Item A                 | Main Store - WH   | Dùng Main Store - WH
Item B                 | (trống)           | Dùng default warehouse  
Item C                 | Invalid WH        | Lỗi validation
```

## Ví dụ finished goods

```excel
custom_no | custom_fg_style | custom_fg_size | custom_fg_color | custom_line
PX001     | M007J          | All Size       | All Color       | Md
```

Kết quả: Tất cả items trong nhóm PX001 sẽ có:
- custom_fg_style = "M007J"
- custom_fg_size = "All Size" 
- custom_fg_color = "All Color"
- custom_line = "Md"

## Material Issue Purpose

Các giá trị hợp lệ:
- `Adjust`: Điều chỉnh
- `Deffected`: Hàng lỗi
- `Destroy`: Hủy bỏ
- `Gap`: Chênh lệch
- `Ie`: IE
- `Md`: MD
- `Over`: Thừa
- `Pro`: Sản xuất
- `Pro Return`: Trả về sản xuất
- `Sample`: Mẫu
- `Trimcard`: Thẻ cắt

## Lưu ý quan trọng

- Items phải tồn tại với đúng `custom_item_name_detail`
- Warehouse phải tồn tại nếu chỉ định trong Excel
- Material Issue Purpose phải nằm trong danh sách cho phép
- Qty phải > 0
- Định dạng ngày: YYYY-MM-DD
- Định dạng giờ: HH:MM:SS
- Stock Entry tạo ra ở trạng thái Draft
- Finished goods fields sẽ được format tự động (title case)
- Kiểm tra tồn kho có thể được disable để tăng performance