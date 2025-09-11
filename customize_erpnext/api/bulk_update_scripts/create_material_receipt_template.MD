# Hướng dẫn Import Material Receipt Stock Entry

## Tổng quan
Chức năng import hàng loạt Material Receipt (phiếu nhập kho) từ file Excel vào ERPNext.

## Cấu trúc file Excel

### Cột bắt buộc:
- `custom_item_name_detail`: Tên chi tiết item (phải khớp chính xác trong Item master)
- `custom_no`: Mã nhóm (các dòng cùng mã sẽ tạo thành 1 Stock Entry)
- `qty`: Số lượng nhập (số dương)
- `custom_invoice_number`: Số hóa đơn/chứng từ

### Cột tùy chọn:
- `No`: Số thứ tự
- `posting_date`: Ngày nhập (YYYY-MM-DD)
- `posting_time`: Giờ nhập (HH:MM:SS)
- `t_warehouse`: Kho đích (để trống = dùng kho mặc định)
- `custom_receive_date`: Ngày nhận hàng thực tế
- `custom_note`: Ghi chú

## Logic chọn kho (t_warehouse)

1. **Có t_warehouse trong Excel** → Kiểm tra tồn tại → Dùng kho đó
2. **Không có t_warehouse** → Dùng default warehouse từ Item Default
3. **Cả 2 đều không có** → Báo lỗi

## Quy trình xử lý

### 1. Validation
- Kiểm tra cột bắt buộc
- Kiểm tra item tồn tại
- Kiểm tra warehouse hợp lệ
- Kiểm tra qty > 0

### 2. Import
- Group theo `custom_no`
- Tạo Stock Entry cho mỗi nhóm
- Purpose = "Material Receipt"
- Dùng `t_warehouse` (kho đích)

### 3. Tối ưu
- **Batch processing**: Xử lý nhiều item cùng lúc
- **Caching**: Cache item và warehouse để tăng tốc
- **Progress tracking**: Hiển thị tiến trình cho user

## Khác biệt với Material Issue

| Material Receipt | Material Issue |
|-----------------|----------------|
| Purpose: "Material Receipt" | Purpose: "Material Issue" |
| Dùng `t_warehouse` (kho đích) | Dùng `s_warehouse` (kho nguồn) |
| Nhập kho | Xuất kho |
| Có `custom_receive_date` | Có `custom_material_issue_purpose` |
| Không có finished goods fields | Có finished goods fields |

## File cấu trúc

```
customize_erpnext/
├── api/bulk_update_scripts/
│   ├── create_material_receipt.py          # Logic chính
│   ├── create_material_receipt_template.py # Phục vụ template
│   └── create_material_receipt_template.xlsx # File Excel mẫu
└── public/js/custom_scripts/
    └── stock_entry_list.js                # Giao diện
```

## Cách sử dụng

1. **Tải template**: Click "Download Template" để tải file Excel mẫu
2. **Điền dữ liệu**: Thay thế data mẫu bằng data thật
3. **Upload & Validate**: Upload file và validate dữ liệu
4. **Import**: Nếu validation OK, click "Import" để tạo Stock Entry

## Ví dụ grouping

```excel
custom_no | custom_item_name_detail | qty | custom_invoice_number
MR001     | Item A                 | 100 | INV-001
MR001     | Item B                 | 50  | INV-001
MR002     | Item C                 | 75  | INV-002
```

Kết quả: 
- MR001 → 1 Stock Entry với 2 items
- MR002 → 1 Stock Entry với 1 item

## Ví dụ warehouse

```excel
custom_item_name_detail | t_warehouse     | Kết quả
Item A                 | Main Store - WH  | Dùng Main Store - WH
Item B                 | (trống)          | Dùng default warehouse
Item C                 | Invalid WH       | Lỗi validation
```

## Lưu ý quan trọng

- Items phải tồn tại với đúng `custom_item_name_detail`
- Warehouse phải tồn tại nếu chỉ định trong Excel
- Qty phải > 0
- Định dạng ngày: YYYY-MM-DD
- Định dạng giờ: HH:MM:SS
- Stock Entry tạo ra ở trạng thái Draft